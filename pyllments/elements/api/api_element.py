import asyncio
from asyncio import Future
from inspect import signature
from typing import Any

import param
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import create_model
from pydantic._internal._model_construction import ModelMetaclass

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.common.app_registry import AppRegistry
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.elements.flow_control import FlowController
from pyllments.ports import InputPort


class APIElement(Element):
    """
    Element that adds API routes to the LLM system
    """
    input_map = param.Dict(default={}, doc="""
        A mapping of input ports names to the expected payload types.
        input_map = {
            'port_a': MessagePayload,
            'port_b': list[MessagePayload]
        }
        """)
    
    response_dict = param.Dict(default={}, doc="""
        A mapping of input port names to the key-value pairs of the generated API response.
        This mapping is used after all of the specified input ports have received a payload,
        at which point, their payloads are aggregated to build the API response and then the
        stored payloads are cleared.

        response_dict = {
            # 'alias' is the key in the API response corresponding to the payload attribute
            # retrieved from the payload at the respective input port e.g. payload.model.attribute_name;
            # a lambda or async function can also be provided to retrieve/format the attribute.
            'port_a': {'alias': 'attribute_name'},
            'port_b': {'another_alias': lambda payload: payload.model.another_attribute_name}
        }
        """)

    trigger_map = param.Dict(default={}, doc="""
        A mapping of output port names to the callback function and the list of input ports to take into account
        before using the callback_fn to output a dictionary to the API.
        The arguments in the callback_fn are Payloads from the respective ports - their names are the port names.
        def callback_fn(port_a, port_b):
            return {
                'alias': attribute_name,
                'another_alias': another_attribute_name
            }
        trigger_map = {
            'port_a': (callback_fn, ['port_a', 'port_b'])
        }
        """)

    build_fn = param.Callable(default=None, doc="""
        A more advanced alternative to the build_map.
        A function used to provide conditional control to the API creation process.
        This function is run every time an input port receives a payload, where that input port is specified
        as the active_input_port.
        The other arguments are the port names as specified in the (connected_)input_map, and c, a dictionary
        which persists between the build_fn calls.
        def build_fn(port_a, port_b, active_input_port, c):
            if active_input_port == port_a:
                return {
                    'alias': port_a.payload.model.attribute_name,
                    'another_alias': port_b.payload.model.another_attribute_name
                }
            else:
                return {
                    'another_alias': port_b.payload.model.another_attribute_name
                }
        """)

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    request_output_fn = param.Callable(default=None, doc="""
        A function used to package the request dictionary into the desired payload type.
        def request_output_fn(key1, key2) -> MessagePayload:
            role = do_something(key1)
            message = do_something_else(key2)
            return MessagePayload(role=role, message=message)
        """
    )

    request_pydantic_model = param.ClassSelector(class_=ModelMetaclass, doc="""
        A Pydantic model used to validate the request dictionary. By default,
        this is dynamically created based on the argument names of request_output_fn.
        """)                                 

    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An optional input port to connect upon initialization that connects to the api_output port of the APIElement.""")

    app = param.ClassSelector(class_=FastAPI, doc="""
        The FastAPI app object for the API. Defaults to the FastAPI app in AppRegistry.""")

    endpoint = param.String(default="api", doc="""
        The endpoint for the API.""")
    
    response_future = param.ClassSelector(class_=Future, doc="""
        The future object for the API response.""")
    
    test = param.Boolean(default=False, doc="""
        Used to test the API route, minimally.
        """)

    stored_kwargs = param.Dict(default={}, doc="Storage for complete kwargs from flow_fn")

    timeout = param.Number(default=30.0, doc="Timeout for API requests in seconds.")

    _is_processing = param.Boolean(default=False, doc="Internal flag to serialize trigger processing and HTTP requests.")

    loop = param.Parameter(default=LoopRegistry.get_loop(), doc="The event loop to use for the API.")

    def __init__(self, **params):
        super().__init__(**params)
        self.app = AppRegistry.get_app()
        # self.model = APIModel(**params)
        if not self.test:   
            self._flow_controller_setup()
            if not self.request_pydantic_model:
                self._create_request_pydantic_model()
            self._route_setup()
        else:
            @self.app.post(f"/{self.endpoint}")
            async def test_post(item: dict):
                return {'sent_request': item}
        if self.outgoing_input_port:
            self.ports.output['api_output'] > self.outgoing_input_port

    def _flow_controller_setup(self):
        if not self.input_map:
            raise ValueError("input_map must be provided.")

        # 1. Setup flow map with persist flags for all input ports
        flow_map = self._flow_map_setup(self.input_map)
        
        # 2. Create a simplified flow_fn 
        def api_flow_fn(**kwargs):
            # Serialize triggers: ignore if already processing
            if self._is_processing:
                return None
            self._is_processing = True
            result = None
            try:
                active_input_port = kwargs['active_input_port']
                c = kwargs.get('c', {})
                port_name = active_input_port.name
                
                # Handle response_dict logic
                if self.response_dict and self._check_required_ports(self.response_dict.keys()):
                    result = self._process_response_dict()
                    return result
                
                # Handle trigger_map logic
                if self.trigger_map and port_name in self.trigger_map:
                    callback_fn, required_ports = self.trigger_map[port_name]
                    if self._check_required_ports(required_ports):
                        result = self._process_trigger_callback(callback_fn, required_ports)
                        return result
                    
                # Handle build_fn logic
                if self.build_fn:
                    return self._process_build_fn(
                        active_input_port=active_input_port, 
                        c=c, 
                        **{k: v for k, v in kwargs.items() if k not in ['active_input_port', 'c']}
                    )
            finally:
                # Clear non-persistent ports after a successful response or None
                # Remove payloads for ports that are not persistent
                for name, cfg in self.input_map.items():
                    if isinstance(cfg, dict) and not cfg.get('persist', True):
                        port = self.flow_controller.flow_port_map.get(name)
                        if port:
                            port.payload = None
                self._is_processing = False
            return result
        
        self.flow_controller = FlowController(
            containing_element=self, 
            flow_map=flow_map,
            flow_fn=api_flow_fn
        )
        self.ports = self.flow_controller.ports

    def _check_required_ports(self, port_names):
        """Check if all required ports have payloads available"""
        return all(
            port_name in self.flow_controller.flow_port_map and 
            self.flow_controller.flow_port_map[port_name].payload is not None
            for port_name in port_names
        )

    def _set_response(self, result):
        """Set the response future if available and not done"""
        if self.response_future and not self.response_future.done():
            self.response_future.set_result(result)
        return result

    def _process_response_dict(self):
        """Process response dictionary and create async task"""
        async def process_response():
            return_dict = {}
            # Build return dictionary using the response_dict mapping
            for port_name, alias_attr_map in self.response_dict.items():
                payload = self.flow_controller.flow_port_map[port_name].payload
                for alias, attr_name in alias_attr_map.items():
                    if isinstance(attr_name, str):
                        # Direct attribute access
                        attr_value = getattr(payload.model, attr_name)
                        return_dict[alias] = attr_value
                    else:  # Function or lambda
                        # Call the function/lambda with the payload
                        result = attr_name(payload)
                        # If it returned a coroutine, await it
                        if asyncio.iscoroutine(result):
                            try:
                                result = await result
                            except Exception as e:
                                self.logger.error(f"Error awaiting coroutine for '{alias}': {e}")
                                result = f"Error: {str(e)}"
                        return_dict[alias] = result
            
            return self._set_response(return_dict)
        
        # Schedule the async task
        self.loop.create_task(process_response())
        return None

    def _process_trigger_callback(self, callback_fn, required_ports):
        """Process a trigger callback function"""
        # Prepare callback kwargs with payloads
        callback_kwargs = {
            port: self.flow_controller.flow_port_map[port].payload
            for port in required_ports
        }
        
        # Handle async callbacks
        if asyncio.iscoroutinefunction(callback_fn):
            async def process_async_callback():
                try:
                    result = await callback_fn(**callback_kwargs)
                    return self._set_response(result)
                except Exception as e:
                    self.logger.error(f"Error in async callback: {e}")
                    raise
            
            # Schedule the async task
            self.loop.create_task(process_async_callback())
            return None
        else:
            try:
                result = callback_fn(**callback_kwargs)
                return self._set_response(result)
            except Exception as e:
                self.logger.error(f"Error in sync callback: {e}")
                raise

    def _process_build_fn(self, active_input_port, c, port_kwargs):
        """Process the build function"""
        # Check if build_fn is async
        if asyncio.iscoroutinefunction(self.build_fn):
            async def process_async_build():
                result = await self.build_fn(
                    active_input_port=active_input_port,
                    c=c,
                    **port_kwargs
                )
                
                if result is not None:
                    return self._set_response(result)
                return None
            
            # Schedule the async task
            self.loop.create_task(process_async_build())
            return None
        else:
            # Synchronous build_fn
            result = self.build_fn(
                active_input_port=active_input_port,
                c=c,
                **port_kwargs
            )
            
            if result is not None:
                return self._set_response(result)
            return None

    def _flow_map_setup(self, input_map):
        """
        Create a flow map from the input_map, ensuring persist flag honors config.
        """
        flow_map = {'input': {}}

        for key, config in input_map.items():
            port_config = None
            
            # Case 1: Direct payload type
            if (isinstance(config, type) and issubclass(config, Payload)) or \
               (hasattr(config, '__origin__') and issubclass(config.__origin__, list)):
                port_config = {
                    'payload_type': config,
                    'persist': True
                }
                
            # Case 2: Dictionary configuration
            elif isinstance(config, dict):
                port_config = config.copy()
                # Allow per-port persistence: default True unless specified False
                port_config['persist'] = config.get('persist', True)
                
                # Ensure we have a way to determine payload_type
                if 'payload_type' not in port_config and ('ports' not in port_config or not port_config['ports']):
                    self.logger.warning(f"Skipping input port '{key}': no payload_type or ports specified")
                    continue
            
            if port_config:
                flow_map['input'][key] = port_config
                
        return flow_map

    def _create_request_pydantic_model(self):
        """Dynamically create a Pydantic model based on the argument names of request_output_fn."""
        sig = signature(self.request_output_fn)
        # TODO: Add type validation
        fields = {param.name: (Any, ...) for param in sig.parameters.values()}
        self.request_pydantic_model = create_model('RequestModel', **fields)   

    def _route_setup(self):
        output_port_payload_type = signature(self.request_output_fn).return_annotation
        # Set up the output port for the Element
        # Define an async callback that handles both sync and async request_output_fn
        async def pack_payload_callback(request_dict: dict) -> output_port_payload_type: # type: ignore
            result = self.request_output_fn(**request_dict)
            if asyncio.iscoroutine(result):
                return await result
            return result
        self.ports.add_output('api_output', pack_payload_callback=pack_payload_callback)
        
        @self.app.post(f"/{self.endpoint}")
        async def post_return(item: self.request_pydantic_model):
            item = item.dict()
            # Check if there's already a request being processed
            self.logger.info(f"Request received: {item}")
            if self.response_future and not self.response_future.done():
                raise HTTPException(
                    status_code=429,
                    detail="Another request is being processed"
                )
            
            self.response_future = asyncio.Future()
            # Await stage_emit as it's now async
            await self.ports.output['api_output'].stage_emit(request_dict=item)
            
            try:
                response = await asyncio.wait_for(
                    self.response_future,
                    timeout=self.timeout
                )
                return response
            except asyncio.TimeoutError:
                self.logger.error(f"Request timed out after {self.timeout} seconds")
                raise HTTPException(
                    status_code=408,
                    detail=f"Request timed out after {self.timeout} seconds"
                )
            finally:
                self.response_future = None