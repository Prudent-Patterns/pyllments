from collections import UserDict
import param

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.common.param import PayloadSelector
from pyllments.ports.ports import InputPort, OutputPort


class FlowPort(param.Parameterized):
    """Special Port wrapper for port management in the flow controller"""

    payload_type = param.Parameter(doc="""
        Payload type for this port""")
    
    def __init__(self, payload_type: type, **params):
        super().__init__(**params)
        self.payload_type = payload_type


class OutputFlowPort(FlowPort):
    """Special OutputPort wrapper for port management in the flow controller"""

    output_port = param.ClassSelector(class_=OutputPort, doc="""
        Output port the flow port wraps""")

    def emit(self, payload: Payload):
        self.output_port.stage_emit(payload=payload)


class InputFlowPort(FlowPort):
    """Special InputPort wrapper for port management in the flow controller"""

    input_port = param.ClassSelector(class_=InputPort, doc="""
        Input port the flow port wraps""")
    
    payload = param.ClassSelector(default=None, class_=Payload, doc="""
        Most recent payload that arrived at this port.
        Removed after ingested by the flow_fn.
        `new` flag is used to help caller determine if a new payload exists""")
    

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
    """

    flow_fn = param.Callable(doc="""
        User-provided callback to run every time a new input payload is received
        Looks like:
        def flow_fn(active_input_port, c, input_alias, output_alias):
            ...
        where the input and output aliases are the port aliases you created in
        the flow_map or connected_flow_map
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

    def __init__(self, **params):
        super().__init__(**params)
        self._setup_ports()

    def _setup_ports(self):
        for io_type in ['input', 'output']:
            # Ensure flow_map has entries for both 'input' and 'output'
            if io_type not in self.flow_map:
                self.flow_map[io_type] = {}

            # Setup ports from flow_map (payload types)
            for alias, payload_type in self.flow_map[io_type].items():
                self._setup_port_from_type(io_type, alias, payload_type)
            
            # Setup ports from connected_flow_map (existing ports)
            for alias, ports in self.connected_flow_map.get(io_type, {}).items():
                ports = [ports] if not isinstance(ports, list) else ports
                if alias not in self.flow_map[io_type]:
                    # If the alias is not in flow_map, infer the payload type and add it to flow_map
                    payload_type = ports[0].payload_type if ports else None
                    if payload_type:
                        self.flow_map[io_type][alias] = payload_type
                        self._setup_port_from_type(io_type, alias, payload_type)
                    else:
                        raise ValueError(f"Cannot infer payload type for {io_type} port '{alias}'")
                
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
        
        self.flow_port_map[alias] = InputFlowPort(payload_type=payload_type)
        
        def unpack(payload: payload_type):
            self._invoke_flow(alias, payload)
        
        input_port = self.ports.add_input(alias, unpack_payload_callback=unpack)
        self.flow_port_map[alias].input_port = input_port

    def _setup_output_port(self, alias, payload_type):
        if alias.startswith('multi_'):
            self.flow_port_map[alias] = {}
            return

        def pack(payload: payload_type) -> payload_type:
            return payload
        
        output_port = self.ports.add_output(alias, pack_payload_callback=pack)
        
        self.flow_port_map[alias] = OutputFlowPort(
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
            input_port=input_port
        )
        input_flow_port.payload_type = port_type

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
                raise KeyError(f"No flow port found with in {alias} with name '{input_port_name}'.")
        else:
            try:
                flow_port = self.flow_port_map[input_port_name]
            except KeyError:
                raise KeyError(f"No flow port found with alias '{input_port_name}'.")

        flow_port.payload = payload
        self.flow_fn(
            active_input_port=flow_port,
            c=self.context,
            **self.flow_port_map.list_view()
        )
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