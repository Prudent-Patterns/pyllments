from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.elements.flow_control import FlowController
from pyllments.ports import InputPort
# from pyllments.ports import Ports
# from .api_model import APIModel

import param
from asyncio import Future
from fastapi import FastAPI, HTTPException
import asyncio
from inspect import signature
from loguru import logger
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
        A mapping of output port names to the key, value pairs of the generated API response.
        Is created when all of the input ports have received a payload, after which, it is cleared.

        response_dict = {
        # attribute_name is retrieved from the payload at the respective port e.g. payload.model.attribute_name
        # lambda function can be provided to retrieve the attribute_name from the payload
            'port_a': {'alias': 'attribute_name'}
            'port_b': {'another_alias': 'another_attribute_name'}
        }
        """)

    build_map = param.Dict(default={}, doc="""
        A mapping of output port names to the callback function and the list of input ports to take into account
        before using the callback_fn to output a dictionary to the API.
        The arguments in the callback_fn are Payloads from the respective ports - their names are the port names.
        def callback_fn(port_a_payload, port_b_payload):
            return {
                'alias': attribute_name,
                'another_alias': another_attribute_name
            }
        build_map = {
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

    output_pack_fn = param.Callable(default=None, doc="""
        A function used to package the output dictionary into the desired payload type. e.g.
        def output_pack_fn(request_dict):
            return MessagePayload(
            mode='system',
            message= )
        """)

    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An optional input port to connect upon initialization.""")

    app = param.ClassSelector(class_=FastAPI, doc="""
        The FastAPI app object for the API.""")

    endpoint = param.String(default="api", doc="""
        The endpoint for the API.""")
    
    response_future = param.ClassSelector(class_=Future, doc="""
        The future object for the API response.""")
    
    test = param.Boolean(default=False)

    stored_kwargs = param.Dict(default={}, doc="Storage for complete kwargs from flow_fn")

    def __init__(self, **params):
        super().__init__(**params)
        # self.model = APIModel(**params)
        if not self.test:   
            self._flow_controller_setup()
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
        flow_map = self._flow_map_setup(self.input_map)
        flow_controller_kwargs['flow_map'] = flow_map
        if self.connected_input_map:
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            flow_controller_kwargs['connected_flow_map'] = connected_flow_map
        self.flow_controller = FlowController(containing_element=self, **flow_controller_kwargs)
        # _flow_fn_setup requires the FlowController to be setup beforehand
        self.flow_controller.flow_fn = self._flow_fn_setup()

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

    def _flow_fn_setup(self):
        async def async_flow_fn(**kwargs):
            active_input_port = kwargs['active_input_port']
            c = kwargs['c']
            
            return_dict = {}
            if self.build_fn:
                return_dict = self.build_fn(**kwargs)
            elif self.build_map:
                input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
                
                # Store incoming payload
                input_name_payload_dict[active_input_port.name] = active_input_port.payload
                
                if c.get('is_ready', True):
                    if active_input_port.name in self.build_map:
                        callback_fn, required_ports = self.build_map[active_input_port.name]
                        c['callback_fn'] = callback_fn
                        c['required_ports'] = required_ports
                        c['is_ready'] = False
                    else:
                        return
                else:
                    callback_fn = c['callback_fn']
                    required_ports = c['required_ports']

                # Check if we have all required payloads
                if all(key in input_name_payload_dict for key in required_ports):
                    # Create kwargs dict for callback function using port names
                    callback_kwargs = {
                        port_name: input_name_payload_dict[port_name] 
                        for port_name in required_ports
                    }
                    
                    # Call callback function with collected payloads
                    return_dict = callback_fn(**callback_kwargs)
                    
                    # Clear processed payloads
                    for key in required_ports:
                        input_name_payload_dict.pop(key, None)
                    c['is_ready'] = True
            elif self.response_dict:
                # Add debug logging
                logger.debug(f"[APIElement] Processing response_dict with active port: {active_input_port.name}")
                input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
                
                # Store incoming payload
                input_name_payload_dict[active_input_port.name] = active_input_port.payload
                
                # Add debug logging
                logger.debug(f"[APIElement] Current stored payloads: {list(input_name_payload_dict.keys())}")
                logger.debug(f"[APIElement] Required ports: {list(self.response_dict.keys())}")
                
                # Check if we have all required payloads defined in response_dict
                if all(port_name in input_name_payload_dict for port_name in self.response_dict.keys()):
                    logger.info("[APIElement] All required payloads received, building response")
                    # Build return dictionary using the response_dict mapping
                    for port_name, alias_attr_map in self.response_dict.items():
                        payload = input_name_payload_dict[port_name]
                        for alias, attr_name in alias_attr_map.items():
                            if isinstance(attr_name, str):
                                return_dict[alias] = getattr(payload.model, attr_name)
                            else:  # In case of lambda function or async function being provided
                                if asyncio.iscoroutinefunction(attr_name):
                                    return_dict[alias] = await attr_name(payload)
                                else:
                                    return_dict[alias] = attr_name(payload)
                    
                    # Clear stored payloads after processing
                    input_name_payload_dict.clear()

            # Set the response future if we have a return dictionary
            if return_dict:
                logger.info(f"[APIElement] Setting response future to {return_dict}")
                if self.response_future and not self.response_future.done():
                    self.response_future.set_result(return_dict)
                else:
                    logger.warning("[APIElement] Response future not available or already done")

        def flow_fn(**kwargs):
            # Return the task directly - FlowController will handle clearing after completion
            return asyncio.create_task(async_flow_fn(**kwargs))

        return flow_fn

    def _route_setup(self):
        output_port_payload_type = signature(self.output_pack_fn).return_annotation
        # Set up the output port for the Element
        def pack_payload_callback(request_dict: dict) -> output_port_payload_type:
            return self.output_pack_fn(request_dict)
        self.ports.add_output('api_output', pack_payload_callback=pack_payload_callback)

        @self.app.post(f"/{self.endpoint}")
        async def post_return(item: dict):
            # Check if there's already a request being processed
            logger.info(f"[APIElement] Request received: {item}")
            if self.response_future and not self.response_future.done():
                raise HTTPException(
                    status_code=429, 
                    detail="Another request is being processed"
                )
            
            # Create new future for this request
            self.response_future = asyncio.Future()
            
            # Emit request through output port
            self.ports.output['api_output'].stage_emit(request_dict=item)
            
            try:
                # Wait for response with timeout
                response = await asyncio.wait_for(
                    self.response_future,
                    timeout=30.0
                )
                return response
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=408, 
                    detail="Request timeout"
                )
            finally:
                # Clear the future
                self.response_future = None