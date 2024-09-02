from types import FunctionType

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, OutputPort, Ports
from pyllments.base.payload_base import Payload
from pyllments.elements.context_builder.to_message import to_message_payload, payload_message_mapping

class ContextBuilder(param.Parameterized):
    # TODO Add ports for the preset messages for additional modularity
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping input keys to expected payload types. Determines the order of the output in
        base case when build_fn not provided.
        Special prefixes: 'system_', 'human_', 'ai_' create messages of that type with the string you provide.
        e.g. 
        input = {
            'port_a': ('human', MessagePayload),
            'port_b': ('ai', List[MessagePayload]), # list will be expanded
            'system_msg': ('system', "This text will be a sys message") # can be system/human/ai
	    }
        """)
    connected_input_map = param.Dict(default={}, doc="""
        A dictionary mapping input keys to the input ports to be connected to the flow controller. Infers
        the input port type from the ports provided in the connected input map.
        e.g.
        connected_input_map = {
            'port_a': ('human',[el1.ports.output['some_output']]),
            'port_b': ('ai',[el2.ports.output['some_output']]),
            'system_msg': ('system', "This text will be a sys message")
        }
        """)

    build_map = param.Dict(default={}, doc="""
        A dictionary mapping between a port alias and a list of ports and messages that sets the key 
        port as the trigger to exhaustively build messages in the order of the provided list(value).
        e.g.
        build_map = {
            'port_a': ['port_a', 'port_b', 'system_msg'],
            'port_b': ['port_b', 'system_msg']
        }
        When a payload enters port_a first, we wait until a payload at port_b is received, then we build
        the messages in the order of the list and emit them, with system_msg being what you specified in
        the input_map. When a payload enters port_b first, the message payloads are instantly built, since
        we have nothing else to wait for.
        """)
    
    build_fn = param.Callable(default=None, doc="""
        A more advanced alternative to the build_map.
        A function used to provide conditional control to the context creation process.
        e.g.
        def build_fn(port_a, port_b, system_msg, active_input_port, c):
            if active_input_port == port_a:
                return [port_a, port_b, system_msg]
            else:
                return [port_b, system_msg]
        """)

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An optional input port to connect to the flow controller's output upon initialization.""")
    
    preset_messages = param.Dict(default={}, doc="""
        Mapping between the specific message aliases in the input_map or connected_input_map and the 
        typed messages to be used during construction of the MessagePayload list.""")
    
    payload_message_mapping = param.Dict(default=payload_message_mapping, doc="""
        Mapping between payload types and message conversion functions.""")

    ports = param.ClassSelector(class_=Ports, doc="""
        The ports object for the context builder from the flow controller.""")

    def __init__(self, **params):
        super().__init__(**params)
        self._flow_controller_setup()
        if self.outgoing_input_port:
            self.connect_output(self.outgoing_input_port)
        self.ports = self.flow_controller.ports

    def _flow_controller_setup(self):
        if not (self.input_map or self.connected_input_map):
            raise ValueError("At least one of input_map or connected_input_map must be provided.")
        
        if self.input_map and self.connected_input_map:
            flow_map = self._flow_map_setup(self.input_map)
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            self.flow_controller = FlowController(
                flow_map=flow_map,
                connected_flow_map=connected_flow_map
            )
        elif self.connected_input_map:
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            self.flow_controller = FlowController(
                connected_flow_map=connected_flow_map
            )
        elif self.input_map:
            flow_map = self._flow_map_setup(self.input_map)
            self.flow_controller = FlowController(
                flow_map=flow_map
            )
        else:
            raise ValueError("Either input_map or connected_input_map must be provided, but not both.")
        
        flow_fn = self._flow_fn_setup()
        self.flow_controller.flow_fn = flow_fn

    def _flow_map_setup(self, input_map):
        flow_map = {'input': {}, 'output': {'messages_output': list[MessagePayload]}}
        for key, (msg_type, payload_type) in input_map.items():
            if (isinstance(payload_type, type) and issubclass(payload_type, Payload)) or \
            (hasattr(payload_type, '__origin__') and issubclass(payload_type.__origin__, list)):
                flow_map['input'][key] = payload_type
            elif isinstance(payload_type, str):
                self.preset_messages[key] = self._create_message(msg_type, payload_type)
        return flow_map

    def _connected_flow_map_setup(self, connected_input_map):
        connected_flow_map = {'input': {}, 'output': {}}
        
        # Handle input connections
        if 'input' in connected_input_map:
            for key, (msg_type, ports_or_string) in connected_input_map['input'].items():
                if isinstance(ports_or_string, (list, tuple)):
                    connected_flow_map['input'][key] = ports_or_string
                    if key not in self.input_map:
                        self.input_map[key] = (msg_type, list[ports_or_string[0].payload_type])
                elif isinstance(ports_or_string, OutputPort):
                    connected_flow_map['input'][key] = [ports_or_string]
                    if key not in self.input_map:
                        self.input_map[key] = (msg_type, ports_or_string.payload_type)
                elif isinstance(ports_or_string, str):
                    msg_string = ports_or_string
                    if not self.preset_messages.get(key):
                        self.preset_messages[key] = self._create_message(msg_type, msg_string)
                    if key not in self.input_map:
                        self.input_map[key] = (msg_type, msg_string)
                else:
                    raise ValueError(f"Invalid value for input key '{key}': {ports_or_string}")
        
        # Handle output connections
        if 'output' in connected_input_map:
            for key, ports in connected_input_map['output'].items():
                if isinstance(ports, (list, tuple)):
                    connected_flow_map['output'][key] = ports
                elif isinstance(ports, InputPort):
                    connected_flow_map['output'][key] = [ports]
                else:
                    raise ValueError(f"Invalid value for output key '{key}': {ports}")
        
        return connected_flow_map

    def _flow_fn_setup(self):
        """Sets up the flow function for the flow controller"""
        flow_map_args = [
            *list(self.flow_controller.flow_map['input'].keys()),
            'active_input_port',
            'c',
            'messages_output'
        ]
    
        def validate_build_map(build_map):
            for input_port_name, input_items in build_map.items():
                if input_port_name not in self.input_map:
                    raise ValueError(f"Input port {input_port_name} not found in input_map")
                for input_item in input_items:
                    if input_item not in self.input_map:
                        raise ValueError(f"Input item {input_item} not found in input_map")
                     
        validate_build_map(self.build_map)
        preset_messages_kwargs = [f"{k}=self.preset_messages['{k}']" for k in self.preset_messages.keys()]
        flow_map_kwargs = [f"{k}=self.flow_controller.flow_port_map['{k}']" for k in self.flow_controller.flow_port_map.keys()]
        other_kwargs = ["c=c", "active_input_port=active_input_port"]
        # code is meant to run every time a new input payload is received
        code = f"""
def flow_fn({', '.join(flow_map_args)}):
    if self.build_fn:
        print("{', '.join(flow_map_kwargs + preset_messages_kwargs + other_kwargs)}")
        self.build_fn({', '.join(flow_map_kwargs + preset_messages_kwargs + other_kwargs)})
    elif self.build_map:
        input_port_keys = c.setdefault(
            'input_port_keys',
            [key for key in self.flow_controller.flow_port_map.keys()
            if key != 'messages_output']
        )
        input_name_payload_dict = c.setdefault('input_name_payload_dict', {{}})
        
        if c.get('is_ready', True):
            input_keys_subset = self.build_map[active_input_port.name]
            input_port_keys_subset = [key for key in input_keys_subset if key in input_port_keys]
            c['input_keys_subset'] = input_keys_subset
            c['input_port_keys_subset'] = input_port_keys_subset
            c['is_ready'] = False
        else:
            input_keys_subset = c['input_keys_subset']
            input_port_keys_subset = c['input_port_keys_subset']

        if active_input_port.name in input_keys_subset:
            input_name_payload_dict[active_input_port.name] = active_input_port.payload

            if all([key in input_name_payload_dict for key in input_port_keys_subset]):
                msg_payload_list = [
                    to_message_payload(input_name_payload_dict[key], self.payload_message_mapping)
                    if not isinstance(self.input_map[key][1], str)
                    else to_message_payload(self.preset_messages[key], self.payload_message_mapping)
                    for key in input_keys_subset
                ]
                messages_output.emit(msg_payload_list)
                c['is_ready'] = True
                c['input_name_payload_dict'].clear()
    else:
        input_port_keys = c.setdefault(
            'input_port_keys',
                [key for key in self.flow_controller.flow_port_map.keys()
                if key != 'messages_output']
        )
        input_name_payload_dict = c.setdefault('input_name_payload_dict', {{}})
        input_name_payload_dict[active_input_port.name] = active_input_port.payload
        if all([key in input_name_payload_dict for key in input_port_keys]):
            msg_payload_list = [
                to_message_payload(input_name_payload_dict[key], self.payload_message_mapping)
                if not isinstance(self.input_map[key][1], str)
                else to_message_payload(self.preset_messages[key], self.payload_message_mapping)
                for key in self.input_map.keys()
            ]
            messages_output.emit(msg_payload_list)
            input_name_payload_dict.clear()
        """
        compiled_code = compile(code, 'context_builder_element.py', 'exec')
        flow_fn = FunctionType(
            compiled_code.co_consts[0],
            {'self': self, 'to_message_payload': to_message_payload}
        )
        return flow_fn

    def _create_message(self, msg_type, text):
        match msg_type:
            case 'human':
                return HumanMessage(content=text)
            case 'ai':
                return AIMessage(content=text)
            case 'system':
                return SystemMessage(content=text)
            case _:
                raise ValueError(f"Invalid message type: {msg_type}")