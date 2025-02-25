import asyncio
from asyncio import Future
from inspect import signature
from typing import Any

import param
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel, create_model
from pydantic._internal._model_construction import ModelMetaclass

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.serve.app_registry import AppRegistry
from pyllments.elements.flow_control import FlowController
from pyllments.ports import InputPort
# from pyllments.ports import Ports
# from .api_model import APIModel


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
    
    connected_input_map = param.Dict(default={}, doc="""
        A mapping of input ports names to the input ports to be connected to the flow controller.
        connected_input_map = {
            'port_a': [el1.ports.output['some_output']],
            'port_b': [el2.ports.output['some_output']]
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
        if not (self.input_map or self.connected_input_map):
            raise ValueError("At least one of input_map or connected_input_map must be provided.")
        
        flow_controller_kwargs = {}
        
        # 1. Setup basic flow maps
        flow_map = self._flow_map_setup(self.input_map)
        flow_controller_kwargs['flow_map'] = flow_map
        
        if self.connected_input_map:
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            flow_controller_kwargs['connected_flow_map'] = connected_flow_map

        # 2. Create a custom flow_fn to handle our trigger_map and response_dict logic
        async def api_flow_fn(**kwargs):
            active_input_port = kwargs['active_input_port']
            c = kwargs.get('c', {})
            port_name = active_input_port.name
            
            # Store the incoming payload
            input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
            input_name_payload_dict[port_name] = active_input_port.payload
            
            # Store all kwargs for potential troubleshooting
            self.stored_kwargs = kwargs
            
            # Handle response_dict logic if defined
            if self.response_dict:
                # Check if we have all required payloads
                if all(port_name in input_name_payload_dict for port_name in self.response_dict.keys()):
                    return_dict = {}
                    # Build return dictionary using the response_dict mapping
                    for port_name, alias_attr_map in self.response_dict.items():
                        payload = input_name_payload_dict[port_name]
                        for alias, attr_name in alias_attr_map.items():
                            if isinstance(attr_name, str):
                                return_dict[alias] = getattr(payload.model, attr_name)
                            else:  # Handle lambda or async function
                                result = attr_name(payload)
                                # If the result is a coroutine, await it.
                                if asyncio.iscoroutine(result):
                                    result = await result
                                return_dict[alias] = result
                    
                    # Set response future if available
                    if self.response_future and not self.response_future.done():
                        self.response_future.set_result(return_dict)
                    
                    # Clear stored payloads after processing
                    input_name_payload_dict.clear()
                    return return_dict
            
            # Handle trigger_map logic if defined
            if self.trigger_map and port_name in self.trigger_map:
                callback_fn, required_ports = self.trigger_map[port_name]
                
                # Check if we have all required payloads
                if all(port in input_name_payload_dict for port in required_ports):
                    # Prepare callback kwargs with payloads
                    callback_kwargs = {
                        port: input_name_payload_dict[port]
                        for port in required_ports
                    }
                    
                    # Handle async callbacks
                    if asyncio.iscoroutinefunction(callback_fn):
                        try:
                            result = await callback_fn(**callback_kwargs)
                            # Set response future if available
                            if self.response_future and not self.response_future.done():
                                self.response_future.set_result(result)
                            # Clean up after processing
                            for port in required_ports:
                                input_name_payload_dict.pop(port, None)
                            return result
                        except Exception as e:
                            logger.error(f"Error in async callback: {e}")
                            raise
                    else:
                        try:
                            result = callback_fn(**callback_kwargs)
                            # Set response future if available
                            if self.response_future and not self.response_future.done():
                                self.response_future.set_result(result)
                            # Clean up after processing
                            for port in required_ports:
                                input_name_payload_dict.pop(port, None)
                            return result
                        except Exception as e:
                            logger.error(f"Error in sync callback: {e}")
                            raise
                            
            # If we have build_fn, use it
            if self.build_fn:
                # Add active_input_port and context to kwargs
                result = self.build_fn(
                    active_input_port=active_input_port,
                    c=c,
                    **input_name_payload_dict
                )
                
                if result is not None:
                    # Set response future if available
                    if self.response_future and not self.response_future.done():
                        self.response_future.set_result(result)
                    return result
            
            return None
        
        flow_controller_kwargs['flow_fn'] = api_flow_fn
        self.flow_controller = FlowController(containing_element=self, **flow_controller_kwargs)
        self.ports = self.flow_controller.ports

    def _flow_map_setup(self, input_map):
        flow_map = {'input': {}}
        for key, (msg_type, payload_type) in input_map.items():
            if (isinstance(payload_type, type) and issubclass(payload_type, Payload)) or \
            (hasattr(payload_type, '__origin__') and issubclass(payload_type.__origin__, list)):
                flow_map['input'][key] = payload_type
        return flow_map

    def _connected_flow_map_setup(self, connected_input_map):
        connected_flow_map = {'input': {}}
        for key, ports in connected_input_map.items():
            connected_flow_map['input'][key] = ports
        return connected_flow_map

    def _create_request_pydantic_model(self):
        """Dynamically create a Pydantic model based on the argument names of request_output_fn."""
        sig = signature(self.request_output_fn)
        # TODO: Add type validation
        fields = {param.name: (Any, ...) for param in sig.parameters.values()}
        self.request_pydantic_model = create_model('RequestModel', **fields)   

    def _route_setup(self):
        output_port_payload_type = signature(self.request_output_fn).return_annotation
        # Set up the output port for the Element
        def pack_payload_callback(request_dict: dict) -> output_port_payload_type: # type: ignore
            return self.request_output_fn(**request_dict)
        self.ports.add_output('api_output', pack_payload_callback=pack_payload_callback)
        
        @self.app.post(f"/{self.endpoint}")
        async def post_return(item: self.request_pydantic_model):
        # async def post_return(item: dict):
            item = item.dict()
            # Check if there's already a request being processed
            logger.info(f"[APIElement] Request received: {item}")
            if self.response_future and not self.response_future.done():
                raise HTTPException(
                    status_code=429, 
                    detail="Another request is being processed"
                )
            
            self.response_future = asyncio.Future()
            self.ports.output['api_output'].stage_emit(request_dict=item)
            
            try:
                response = await asyncio.wait_for(
                    self.response_future,
                    timeout=self.timeout
                )
                return response
            except asyncio.TimeoutError:
                logger.error(f"[APIElement] Request timed out after {self.timeout} seconds")
                raise HTTPException(
                    status_code=408, 
                    detail=f"Request timed out after {self.timeout} seconds"
                )
            finally:
                self.response_future = None