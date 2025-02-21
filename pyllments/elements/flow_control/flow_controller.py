from collections import UserDict
import param
from typing import Any
import asyncio
from inspect import signature
from loguru import logger

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.common.param import PayloadSelector
from pyllments.ports.ports import InputPort, OutputPort, Ports
# TODO: Reach decision about whether to get rid of InputFlowPorts to avoid stale storage of paylaods - currently
# they payloads are being set to the flowports and not being cleaned up.

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

    def emit(self, payload: Payload):
        self.output_port.stage_emit(payload=payload)

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
    Takes a user-provided callback which is meant to run every time a new
    input payload is received -- as well as maps for input and output payload types
    or ports to be used in the callback signature.
    Either flow_map or connected_flow_map should be provided to set up the ports.
    Can also create multi-ports which take a variable amount of connections, and
    create a new port and connection for each.

    Connecting ports after instantiation:
    1. Using the '>' operator (standard Element connection):
       element1.ports.output['some_output'] > flow_controller.ports.input['input_alias']
       flow_controller.ports.output['output_alias'] > element2.ports.input['some_input']

    2. Using connect_input and connect_output methods:
       flow_controller.connect_input('input_alias', element1.ports.output['some_output'])
       flow_controller.connect_output('output_alias', element2.ports.input['some_input'])

    3. For multi-ports:
       flow_controller.connect_input('multi_input_alias', element1.ports.output['output1'])
       flow_controller.connect_input('multi_input_alias', element2.ports.output['output2'])

    4. Connecting multiple ports at once:
       flow_controller.connect_inputs({
           'input_alias1': [element1.ports.output['output1'], element2.ports.output['output2']],
           'input_alias2': [element3.ports.output['output3']]
       })
       flow_controller.connect_outputs({
           'output_alias1': [element4.ports.input['input1'], element5.ports.input['input2']],
           'output_alias2': [element6.ports.input['input3']]
       })

    Note: When using multi-ports, the alias in flow_map should start with 'multi_'.
    For example: 'multi_input_alias': SomePayloadType

    When FlowController is used within an element, it is recommended to assign that element's
    ports to the FlowController's ports parameter in the __init__ method.
    """

    user_flow_fn = param.Callable(doc="""
        User-provided callback to run every time a new input payload is received.
        This has highest priority and will be called before build_map logic.
        """)
    
    flow_fn = param.Callable(doc="""
        The main flow function that combines user_flow_fn and build_map logic.
        This is set up internally by _setup_flow_fn.
        """)
    
    flow_map = param.Dict(default={}, doc="""
        Alias map to the input and output payload types which are to be used in the
        callback signature
        Example of how to structure the flow map:
        {
            'input': {
                'flow_port_input1': MessagePayload,
                'multi_input1': MessagePayload
            },
            'output': {
                'flow_port_output1': MessagePayload,
                'multi_output1': MessagePayload
            }
        }""")
    connected_flow_map = param.Dict(default={}, doc="""
        Alias map to the input and output ports which are to be connected.
        Can be used during instantiation or after instantiation.
        Example of how to structure the connected flow map:
        {
            'input': {
                'flow_port_input1': [el1.ports.output['output1'], el2.ports.output['output2']],
                'multi_input1': [el3.ports.output['output3']]
            },
            'output': {
                'flow_port_output1': [el4.ports.input['input1'], el5.ports.input['input2']],
                'multi_output1': [el6.ports.input['input3']]
            }
        }""")

    flow_port_map = param.ClassSelector(default=FlowPortMap(), class_=FlowPortMap, doc="""
        Alias map to the input and output flow ports which are to be used in the
        callback signature""")
    
    context = param.Dict(default={}, doc="""
        Context for the user to manage""")
    
    containing_element = param.ClassSelector(default=None, class_=Element, doc="""
        Element that contains/uses this flow controller -- useful for self-documenting""")

    build_map = param.Dict(default={}, doc="""
        A mapping of trigger port names to callback functions.
        When a payload arrives at a trigger port, the FlowController will:
        1. Store the payload
        2. Check if all required ports (from callback's arguments) have payloads
        3. Execute the callback with the collected payloads
        4. Clean up the used payloads
        
        Example:
        {
            'trigger_port': lambda port_a, port_b: process_payloads(port_a, port_b)
        }
        
        The callback function's argument names must match port names in the flow_map.
        These arguments automatically define which ports are required.
        """)

    def __init__(self, **params):
        super().__init__(**params)
        if self.containing_element:
            self.ports = Ports(containing_element=self.containing_element)
        self._setup_ports()
        self._setup_flow_fn()

    def _setup_ports(self):
        for io_type in ['input', 'output']:
            if io_type not in self.flow_map:
                self.flow_map[io_type] = {}

            # Combine aliases from both flow_map and connected_flow_map
            all_aliases = set(self.flow_map[io_type].keys()) | set(self.connected_flow_map.get(io_type, {}).keys())

            for alias in all_aliases:
                # Determine payload type
                if alias in self.flow_map[io_type]:
                    payload_type = self.flow_map[io_type][alias]
                elif io_type in self.connected_flow_map and alias in self.connected_flow_map[io_type]:
                    ports = self.connected_flow_map[io_type][alias]
                    ports = [ports] if not isinstance(ports, list) else ports
                    if ports:
                        payload_type = ports[0].payload_type
                    else:
                        # Skip this alias if it has an empty list in connected_flow_map and isn't in flow_map
                        continue
                else:
                    # This case shouldn't occur, but let's handle it just in case
                    raise ValueError(f"Unable to determine payload type for {io_type} port '{alias}'")

                # Set up the port
                self._setup_port_from_type(io_type, alias, payload_type)

                # Connect ports if they're in connected_flow_map
                if io_type in self.connected_flow_map and alias in self.connected_flow_map[io_type]:
                    ports = self.connected_flow_map[io_type][alias]
                    ports = [ports] if not isinstance(ports, list) else ports
                    for port in ports:
                        if io_type == 'input':
                            self.connect_input(alias, port)
                        else:
                            self.connect_output(alias, port)

    def _setup_port_from_type(self, io_type, alias, payload_type):
        if payload_type is None:
            raise ValueError(f"Payload type for {io_type} port '{alias}' cannot be None")
        
        if io_type == 'input':
            self._setup_input_port(alias, payload_type)
        elif io_type == 'output':
            self._setup_output_port(alias, payload_type)

    def _setup_input_port(self, alias, payload_type):
        if alias.startswith('multi_'):
            self.flow_port_map[alias] = {}
            return
        
        def unpack(payload: payload_type):
            self._invoke_flow(alias, payload)
        
        input_port = self.ports.add_input(alias, unpack_payload_callback=unpack)
        
        self.flow_port_map[alias] = InputFlowPort(
            name=alias,
            payload_type=payload_type,
            input_port=input_port
        )

    def _setup_output_port(self, alias, payload_type):
        if alias.startswith('multi_'):
            self.flow_port_map[alias] = {}
            return

        def pack(payload: payload_type) -> payload_type:
            return payload
        
        output_port = self.ports.add_output(alias, pack_payload_callback=pack)
        
        self.flow_port_map[alias] = OutputFlowPort(
            name=alias,
            output_port=output_port,
            payload_type=payload_type
        )

    def connect_input(self, alias: str, other_output_port):
        """
        Connect an input port to an external output port
        Also handles setting up multi-ports
        """
        # Setup for multi-ports triggered upon connection
        if alias.startswith('multi_'):
            # Multiports return the newly created port for custom mappings
            return self._multi_input_setup(alias, other_output_port)
        else:
            other_output_port.connect(self.ports.input[alias])

    def _multi_input_setup(self, alias, other_output_port):
        # Port name uniqueness setting
        port_alias = f"{alias}_0"
        while port_alias in self.ports.input:
            port_alias_num = int(port_alias.rsplit('_')[-1])
            port_alias = f"{alias}_{port_alias_num + 1}"

        port_type = self.flow_map['input'][alias]
        def unpack(payload: port_type):
            self._invoke_flow(port_alias, payload)

        input_port = self.ports.add_input(port_alias, unpack_payload_callback=unpack)
        other_output_port.connect(input_port)

        input_flow_port = InputFlowPort(
            name=port_alias,
            input_port=input_port,
            payload_type=port_type
        )

        self.flow_port_map[alias][port_alias] = input_flow_port
        return input_flow_port

    def _invoke_flow(self, input_port_name: str, payload):
        is_multi = input_port_name.startswith('multi_')
        if is_multi:
            # Make sure to extract alias from port name
            num_suffix = input_port_name.rsplit('_')[-1]
            suffix_idx = input_port_name.rfind(num_suffix)
            alias = input_port_name[:suffix_idx]
            try:
                flow_multi_port = self.flow_port_map[alias]
            except KeyError:
                raise KeyError(f"No flow port found with alias '{alias}'.")
            try:
                flow_port = flow_multi_port[input_port_name]
            except KeyError:
                raise KeyError(f"No flow port found in {alias} with name '{input_port_name}'.")
        else:
            try:
                flow_port = self.flow_port_map[input_port_name]
            except KeyError:
                raise KeyError(f"No flow port found with alias '{input_port_name}'.")

        flow_port.payload = payload
        result = self.flow_fn(
            active_input_port=flow_port,
            c=self.context,
            **self.flow_port_map.list_view()
        )

        # If result is a coroutine/task, create a task that waits for it before clearing
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Task):
            async def clear_after_complete():
                try:
                    await result
                finally:
                    flow_port.payload = None
            asyncio.create_task(clear_after_complete())
        else:
            # Synchronous case - clear immediately as before
            flow_port.payload = None

    def connect_output(self, alias: str, other_input_port):
        """Connect an output port to an external input port"""
        # Setup for multi-ports triggered upon connection
        if alias.startswith('multi_'):
            # Multiports return the newly created port for custom mappings
            return self._multi_output_setup(alias, other_input_port)
        else:
            self.ports.output[alias].connect(other_input_port)

    def _multi_output_setup(self, alias, other_input_port):
        # Port name uniqueness setting
        port_alias = f"{alias}_0"
        while port_alias in self.ports.output:
            port_alias_num = int(port_alias.rsplit('_')[-1])
            port_alias = f"{alias}_{port_alias_num + 1}"
        port_type = self.flow_map['output'][alias]
        def pack(payload: port_type) -> port_type:
            return payload

        output_port = self.ports.add_output(port_alias, pack_payload_callback=pack)
        self.ports.output[port_alias].connect(other_input_port)

        output_flow_port = OutputFlowPort(
            name=port_alias,
            output_port=output_port,
            payload_type=port_type
        )
        self.flow_port_map[alias][port_alias] = output_flow_port
        return output_flow_port

    def connect_inputs(self, input_alias_map: dict[str, list[OutputPort]]):
        """Connect input ports to external output ports"""
        for alias, other_output_ports in input_alias_map.items():
            for other_output_port in other_output_ports:
                self.connect_input(alias, other_output_port)

    def connect_outputs(self, output_alias_map: dict[str, list[InputPort]]):
        """Connect output ports to external input ports"""
        for alias, other_input_ports in output_alias_map.items():
            for other_input_port in other_input_ports:
                self.connect_output(alias, other_input_port)

    def _build_map_flow_fn(self, **kwargs):
        """Internal handler for build_map based flow"""
        if not self.build_map:
            return None
        
        active_input_port = kwargs['active_input_port']
        c = kwargs.get('c', {})
        
        # Store incoming payload
        input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
        input_name_payload_dict[active_input_port.name] = active_input_port.payload
        
        if active_input_port.name in self.build_map:
            callback = self.build_map[active_input_port.name]
            # Get required ports from callback signature
            required_ports = [
                param.name for param in signature(callback).parameters.values()
            ]
            
            # Check if we have all required payloads
            if all(port in input_name_payload_dict for port in required_ports):
                # Execute callback with collected payloads
                callback_kwargs = {
                    port: input_name_payload_dict[port]
                    for port in required_ports
                }
                
                # Handle async callbacks
                if asyncio.iscoroutinefunction(callback):
                    # Return a task that will handle cleanup after completion
                    async def async_callback():
                        try:
                            result = await callback(**callback_kwargs)
                            # Cleanup after async completion
                            for port in required_ports:
                                input_name_payload_dict.pop(port, None)
                            return result
                        except Exception as e:
                            logger.error(f"Error in async callback: {e}")
                            raise
                
                return asyncio.create_task(async_callback())
            else:
                # Synchronous callback
                try:
                    result = callback(**callback_kwargs)
                    # Cleanup immediately for sync callbacks
                    for port in required_ports:
                        input_name_payload_dict.pop(port, None)
                    return result
                except Exception as e:
                    logger.error(f"Error in sync callback: {e}")
                    raise
        return None

    def _setup_flow_fn(self):
        """
        Sets up the main flow function based on configuration.

        This function assigns a callable to self.flow_fn so that when a payload is received,
        the flow controller can process it. If no user_flow_fn or build_map is provided,
        the fallback returns None but still remains callable.
        """
        def flow_fn(**kwargs):
            if self.user_flow_fn:  # Maximum specificity first.
                if asyncio.iscoroutinefunction(self.user_flow_fn):
                    return asyncio.create_task(self.user_flow_fn(**kwargs))
                return self.user_flow_fn(**kwargs)
            elif self.build_map:
                result = self._build_map_flow_fn(**kwargs)
                if result is not None:
                    return result
            # Fallback: do nothing and return None.
            return None

        self.flow_fn = flow_fn
        return flow_fn