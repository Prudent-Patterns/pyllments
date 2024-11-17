from functools import cache

from loguru import logger
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, OutputPort, Ports
from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from .to_message import to_message_payload, payload_message_mapping

class ContextBuilder(Element):
    # TODO Add ports for the preset messages for additional modularity
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping input keys to expected payload types. Determines the order of the output in
        base case when build_fn not provided.
        The value is a tuple where the first element is the message type ('system', 'human', 'ai') and
        the second element is either a Payload type or a string for preset messages.
        e.g. 
        input_map = {
            'port_a': ('human', MessagePayload),
            'port_b': ('ai', list[MessagePayload]), # list will be expanded
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
        flow_controller_kwargs = {}
        flow_map = self._flow_map_setup(self.input_map)
        flow_controller_kwargs['flow_map'] = flow_map
        if self.connected_input_map:
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            flow_controller_kwargs['connected_flow_map'] = connected_flow_map
        self.flow_controller = FlowController(containing_element=self, **flow_controller_kwargs)
        # _flow_fn_setup requires the FlowController to be setup beforehand
        self.flow_controller.flow_fn = self._flow_fn_setup()

    def _flow_map_setup(self, input_map):
        flow_map = {'input': {}, 'output': {'messages_output': list[MessagePayload]}}
        for key, (msg_type, payload_type) in input_map.items():
            if (isinstance(payload_type, type) and issubclass(payload_type, Payload)) or \
            (hasattr(payload_type, '__origin__') and issubclass(payload_type.__origin__, list)):
                flow_map['input'][key] = payload_type
            elif isinstance(payload_type, str):
                self.preset_messages[key] = type(self)._create_message(msg_type, payload_type)
        return flow_map

    def _connected_flow_map_setup(self, connected_input_map):
        connected_flow_map = {'input': {}, 'output': {}}
        
        for key, (msg_type, ports_or_string) in connected_input_map.items():
            if key == 'output':
                # Handle output connections
                for out_key, ports in ports_or_string.items():
                    if isinstance(ports, (list, tuple)):
                        connected_flow_map['output'][out_key] = ports
                    elif isinstance(ports, InputPort):
                        connected_flow_map['output'][out_key] = [ports]
                    else:
                        raise ValueError(f"Invalid value for output key '{out_key}': {ports}")
            else:
                # Handle input connections
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
                    if key not in self.preset_messages:
                        self.preset_messages[key] = type(self)._create_message(msg_type, msg_string)
                    if key not in self.input_map:
                        self.input_map[key] = (msg_type, msg_string)
                else:
                    raise ValueError(f"Invalid value for key '{key}': {ports_or_string}")
        
        return connected_flow_map

    def _flow_fn_setup(self):
        """Sets up the flow function for the flow controller"""
        
        def validate_build_map(build_map):
            for input_port_name, input_items in build_map.items():
                if input_port_name not in self.input_map:
                    raise ValueError(f"Input port {input_port_name} not found in input_map")
                for input_item in input_items:
                    if input_item not in self.input_map:
                        raise ValueError(f"Input item {input_item} not found in input_map")
        
        validate_build_map(self.build_map)

        def flow_fn(**kwargs):
            active_input_port = kwargs['active_input_port']
            c = kwargs['c']
            messages_output = kwargs['messages_output']

            if self.build_fn:
                self.build_fn(**kwargs)
            elif self.build_map:
                input_port_keys = c.setdefault(
                    'input_port_keys',
                    [key for key in self.flow_controller.flow_port_map.keys()
                    if key != 'messages_output']
                )
                input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
                
                # Always store the incoming payload
                input_name_payload_dict[active_input_port.name] = active_input_port.payload
                logger.info(f"[ContextBuilder] Set payload on port {active_input_port.name}: {type(active_input_port.payload)}")
                if c.get('is_ready', True):
                    if active_input_port.name in self.build_map:
                        logger.info(f"[ContextBuilder] Building messages for {active_input_port.name}: {self.build_map[active_input_port.name]}")
                        required_ports = self.build_map[active_input_port.name]
                        input_port_keys_subset = [key for key in required_ports if key in input_port_keys]
                        c['required_ports'] = required_ports
                        c['input_port_keys_subset'] = input_port_keys_subset
                        c['is_ready'] = False
                    else:
                        # If the active port isn't in build_map, we don't start a build sequence
                        return
                else:
                    required_ports = c['required_ports']
                    input_port_keys_subset = c['input_port_keys_subset']

                # Check if we have all required payloads
                if all(key in input_name_payload_dict for key in input_port_keys_subset):
                    msg_payload_list = []
                    for key in required_ports:
                        payload = (
                            to_message_payload(
                            input_name_payload_dict[key], 
                            self.payload_message_mapping,
                            expected_type=self.flow_controller.flow_port_map[key].payload_type
                        )
                        if not isinstance(self.input_map[key][1], str)
                        else self.preset_messages[key]
                        )
                        if isinstance(payload, list):
                            msg_payload_list.extend(payload)
                        else:
                            msg_payload_list.append(payload)

                    for key in required_ports:
                        input_name_payload_dict.pop(key, None)
                    c['is_ready'] = True
                    logger.info(f"[ContextBuilder] Emitting ports: {required_ports}")
                    messages_output.emit(msg_payload_list)
            # Default behavior without build_map or build_fn
            # Waits for all payloads to be received and then emits the messages in the order of the input_map
            else:
                input_port_keys = c.setdefault(
                    'input_port_keys',
                    [key for key in self.flow_controller.flow_port_map.keys()
                    if key != 'messages_output']
                )
                input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
                input_name_payload_dict[active_input_port.name] = active_input_port.payload
                logger.info(f"[ContextBuilder] Set payload on port {active_input_port.name}: {type(active_input_port.payload)}")

                # Convert to MessagePayloads or lists of MessagePayloads, then emit all of them
                if all([key in input_name_payload_dict for key in input_port_keys]):
                    msg_payload_list = []
                    for key in self.input_map.keys():
                        payload = (
                            to_message_payload(
                                input_name_payload_dict[key], 
                                self.payload_message_mapping,
                                expected_type=self.flow_controller.flow_port_map[key].payload_type
                            )
                            if not isinstance(self.input_map[key][1], str)
                            else self.preset_messages[key]
                        )
                        if isinstance(payload, list):
                            msg_payload_list.extend(payload)
                        else:
                            msg_payload_list.append(payload)
                            
                    input_name_payload_dict.clear()
                    messages_output.emit(msg_payload_list)

        return flow_fn

    @staticmethod
    @cache
    def _create_message(msg_type, text):
        match msg_type:
            case 'human':
                return MessagePayload(message=HumanMessage(content=text))
            case 'ai':
                return MessagePayload(message=AIMessage(content=text))
            case 'system':
                return MessagePayload(message=SystemMessage(content=text))
            case _:
                raise ValueError(f"Invalid message type: {msg_type}")
