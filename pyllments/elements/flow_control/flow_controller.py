from collections import UserDict
import param
import asyncio
from loguru import logger
import inspect  # for autodetecting the caller

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.ports.ports import InputPort, OutputPort, Ports
from pyllments.runtime.loop_registry import LoopRegistry


class FlowPort(param.Parameterized):
    """Special Port wrapper for port management in the flow controller"""
    payload_type = param.Parameter(doc="Payload type for this port")
    
    def __init__(self, **params):
        super().__init__(**params)

# Update OutputFlowPort and InputFlowPort similarly
class OutputFlowPort(FlowPort):
    output_port = param.ClassSelector(class_=OutputPort, doc="Output port the flow port wraps")

    def __init__(self, **params):
        super().__init__(**params)

    async def emit(self, payload: Payload):
        await self.output_port.stage_emit(payload=payload)

class InputFlowPort(FlowPort):
    input_port = param.ClassSelector(class_=InputPort, doc="Input port the flow port wraps")
    payload = param.ClassSelector(default=None, class_=(list, Payload), doc="Most recent payload that arrived at this port.")

    def __init__(self, **params):
        super().__init__(**params)
      

class FlowPortMap(UserDict):
    """
    Special dict wrapper that keeps two dicts, with one containing the
    values set as dicts as raw dicts, and a special list-view dict
    which contains the values set as dictionaries as lists of the dict values
    Additionally: Said dictionaries are wrapped within their own dict wrapper
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._list_view_dict = {}
        self._update_list_view_dict()

    def __setitem__(self, key, value):
        if isinstance(value, dict) and not isinstance(value, self._DictWrapper):
            value = self._DictWrapper(self, key, value)
        super().__setitem__(key, value)
        self._update_list_view_item(key, value)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if isinstance(value, dict) and not isinstance(value, self._DictWrapper):
            value = self._DictWrapper(self, key, value)
            super().__setitem__(key, value)
        return value

    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self[k] = v

    def _update_list_view_item(self, key, value):
        if isinstance(value, (dict, self._DictWrapper)):
            self._list_view_dict[key] = list(value.values())
        else:
            self._list_view_dict[key] = value

    def _update_list_view_dict(self):
        for key, value in self.data.items():
            self._update_list_view_item(key, value)

    def list_view(self):
        return self._list_view_dict

    class _DictWrapper(UserDict):
        def __init__(self, parent, key, d):
            self._parent = parent
            self._key = key
            super().__init__(d)

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            self._parent._update_list_view_item(self._key, self)

        def __delitem__(self, key):
            super().__delitem__(key)
            self._parent._update_list_view_item(self._key, self)

        def update(self, *args, **kwargs):
            super().update(*args, **kwargs)
            self._parent._update_list_view_item(self._key, self)

        def clear(self):
            super().clear()
            self._parent._update_list_view_item(self._key, self)


class FlowController(Element):
    """
    Used to control complex flow logic between Elements.
    Takes a flow function which is meant to run every time a new
    input payload is received -- as well as maps for input and output payload types
    or ports to be used in the function signature.
    Either flow_map or connected_flow_map should be provided to set up the ports.

    Connecting ports after instantiation:
    Using the '>' operator (standard Element connection):
       element1.ports.output['some_output'] > flow_controller.ports.input['input_alias']
       flow_controller.ports.output['output_alias'] > element2.ports.input['some_input']

    When FlowController is used within an element, it is recommended to assign that element's
    ports to the FlowController's ports parameter in the __init__ method.
    """

    flow_fn = param.Parameter(default=None, allow_refs=False, doc="""
        Function to run every time a new input payload is received.
        The function should accept an active_input_port parameter, a context parameter 'c',
        and any other flow ports as specified in the flow_map.
        """)
    
    flow_map = param.Dict(default={}, doc="""
        Unified alias map for configuring both payload types and port connections.
        Each I/O type ('input' or 'output') should map aliases to a configuration dictionary.
        For example:
        {
            'input': {
                'chat_input': {
                    'payload_type': MessagePayload,
                    'ports': [el1.ports.output['msg']],
                    'persist': True
                }
            },
            'output': {
                'chat_output': {
                    'payload_type': MessagePayload,
                    'ports': [el2.ports.input['response']]
                }
            }
        }
        """)
    
    flow_port_map = param.ClassSelector(default=FlowPortMap(), class_=FlowPortMap, doc="""
        Alias map to the input and output flow ports which are to be used in the
        callback signature""")
    
    context = param.Dict(default={}, doc="""
        Context for the user to manage""")
    
    containing_element = param.ClassSelector(default=None, class_=Element, doc="""
        Element that contains/uses this flow controller -- useful for self-documenting""")

    def __init__(self, **params):
        if not params.get('containing_element'):
            # grab the previous frame (the caller)
            caller_frame = inspect.currentframe().f_back
            potential_parent = caller_frame.f_locals.get('self')
            # only accept it if it really is an Element
            if isinstance(potential_parent, Element):
                params['containing_element'] = potential_parent

        parent = params.get('containing_element')
        if parent and not params.get('name'):
            params['name'] = f"{parent.name}:FlowController"

        super().__init__(**params)

        if self.containing_element:
            self.ports = Ports(containing_element=self.containing_element)
        self._setup_ports()

    def _setup_ports(self):
        for io_type in ['input', 'output']:
            # Ensure that this I/O type has a configuration dictionary; if not, initialize it.
            if io_type not in self.flow_map:
                self.flow_map[io_type] = {}

            # Process each alias in the unified flow_map for the given I/O type.
            for alias, config in self.flow_map[io_type].items():
                if not isinstance(config, dict):
                    raise ValueError(
                        f"Configuration for {io_type} port '{alias}' must be a dict with 'payload_type' and optional 'ports'."
                    )
                # Attempt to get the payload type directly.
                if "payload_type" not in config:
                    if "ports" in config:
                        ports = config["ports"]
                        ports = ports if isinstance(ports, list) else [ports]
                        if ports:
                            # Infer the payload type from the first port's payload_type
                            payload_type = ports[0].payload_type
                        else:
                            raise ValueError(
                                f"No ports provided to infer payload type for {io_type} port '{alias}'."
                            )
                    else:
                        raise ValueError(
                            f"'payload_type' must be specified in the configuration for {io_type} port '{alias}', or provide ports to infer it."
                        )
                else:
                    payload_type = config["payload_type"]

                # Set up the port based on I/O type and payload type
                self._setup_port_from_type(io_type, alias, payload_type)

                # If external ports are specified, connect them.
                if "ports" in config:
                    ports = config["ports"]
                    ports = ports if isinstance(ports, list) else [ports]
                    for port in ports:
                        if io_type == 'input':
                            port > self.ports.input[alias]
                        else:
                            self.ports.output[alias] > port

    def _setup_port_from_type(self, io_type, alias, payload_type):
        if payload_type is None:
            raise ValueError(f"Payload type for {io_type} port '{alias}' cannot be None")
        
        if io_type == 'input':
            self._setup_input_port(alias, payload_type)
        elif io_type == 'output':
            self._setup_output_port(alias, payload_type)

    def _setup_input_port(self, alias, payload_type):
        def unpack(payload: payload_type):
            self._invoke_flow(alias, payload)
        
        input_port = self.ports.add_input(alias, unpack_payload_callback=unpack)
        
        self.flow_port_map[alias] = InputFlowPort(
            name=alias,
            payload_type=payload_type,
            input_port=input_port
        )

    def _setup_output_port(self, alias, payload_type):
        def pack(payload: payload_type) -> payload_type:
            return payload
        
        output_port = self.ports.add_output(alias, pack_payload_callback=pack)
        
        self.flow_port_map[alias] = OutputFlowPort(
            name=alias,
            output_port=output_port,
            payload_type=payload_type
        )

    def _invoke_flow(self, input_port_name: str, payload):
        try:
            flow_port = self.flow_port_map[input_port_name]
        except KeyError:
            raise KeyError(f"No flow port found with alias '{input_port_name}'.")

        flow_port.payload = payload

        self.logger.debug(f"Invoking flow_fn for input port {input_port_name}")
        result = self.flow_fn(
            active_input_port=flow_port,
            c=self.context,
            **self.flow_port_map.list_view()
        )
        
        # Handle async result by creating a task
        if asyncio.iscoroutine(result):
            # Use the centralized LoopRegistry to schedule the coroutine
            loop = LoopRegistry.get_loop()
            try:
                result_task = loop.create_task(result)

                if not self.flow_map['input'][input_port_name].get('persist', False):
                    async def clear_after_complete():
                        try:
                            await result_task
                        finally:
                            flow_port.payload = None
                    loop.create_task(clear_after_complete())
            except Exception as e:
                self.logger.error(f"Error creating task: {e}")
                if not self.flow_map['input'][input_port_name].get('persist', False):
                    flow_port.payload = None
        elif not self.flow_map['input'][input_port_name].get('persist', False):
            # Synchronous case - clear immediately as before
            flow_port.payload = None
