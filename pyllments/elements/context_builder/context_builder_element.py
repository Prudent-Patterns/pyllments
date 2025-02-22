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

    trigger_map = param.Dict(default={}, doc="""
        A dictionary mapping between a port alias and a list of ports and messages that sets the key 
        port as the trigger to exhaustively build messages in the order of the provided list(value).
        e.g.
        trigger_map = {
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
        An optional input port to connect to the flow controller's output upon initialization.
        Connects to the messages_output port of the flow controller.""")
    
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

        self.ports = self.flow_controller.ports
        if self.outgoing_input_port:
            self.ports.messages_output > self.outgoing_input_port

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

        # 2. Handle trigger_map if present
        if self.trigger_map:
            # Validate trigger_map first
            for trigger_port, required_ports in self.trigger_map.items():
                if trigger_port not in self.input_map:
                    raise ValueError(f"Input port {trigger_port} not found in input_map")
                for port in required_ports:
                    if port not in self.input_map:
                        raise ValueError(f"Input item {port} not found in input_map")

            # Convert ContextBuilder's trigger_map to FlowController's trigger_map format
            flow_controller_trigger_map = {}
            for trigger_port, required_ports in self.trigger_map.items():
                def create_callback(ports):
                    def callback(**kwargs):
                        msg_payload_list = []
                        for key in ports:
                            if isinstance(self.input_map[key][1], str):
                                # Handle preset messages
                                msg_payload_list.append(self.preset_messages[key])
                            else:
                                # Handle port payloads:
                                # Now passing role from the input map to override the default conversion role.
                                payload = kwargs[key]
                                converted = to_message_payload(
                                    payload,
                                    self.payload_message_mapping,
                                    expected_type=self.flow_controller.flow_port_map[key].payload_type,
                                    role=self.input_map[key][0]  # overriding role property
                                )
                                if isinstance(converted, list):
                                    msg_payload_list.extend(converted)
                                else:
                                    msg_payload_list.append(converted)
                        return msg_payload_list
                    return callback

                # Create callback with all ports as arguments
                flow_controller_trigger_map[trigger_port] = create_callback(required_ports)

            flow_controller_kwargs['trigger_map'] = flow_controller_trigger_map

        # 3. Create user_flow_fn if we have build_fn or need default behavior
        if self.build_fn:
            def augmented_build_fn(**kwargs):
                # Get the ordering from the user's build_fn
                result_order = self.build_fn(**kwargs)
                if result_order is None:
                    return None
                
                msg_payload_list = []
                for item in result_order:
                    if isinstance(item, str):
                        # Handle preset message keys
                        if item not in self.preset_messages:
                            raise ValueError(f"No preset message found for key '{item}'")
                        msg_payload_list.append(self.preset_messages[item])
                    else:
                        # Handle port objects (assuming they are flow ports)
                        if not hasattr(item, 'payload'):
                            raise TypeError(f"Expected flow port object or string, got {type(item)}")
                        payload = item.payload
                        if payload is None:
                            continue
                        
                        # Pass role from input_map using item.name
                        converted = to_message_payload(
                            payload,
                            self.payload_message_mapping,
                            expected_type=self.flow_controller.flow_port_map[item.name].payload_type,
                            role=self.input_map[item.name][0]  # overriding role
                        )
                        if isinstance(converted, list):
                            msg_payload_list.extend(converted)
                        else:
                            msg_payload_list.append(converted)
                
                if msg_payload_list:
                    kwargs['messages_output'].emit(msg_payload_list)
                
                return None  # Return None since we handled the emission
            
            flow_controller_kwargs['user_flow_fn'] = augmented_build_fn
        
        elif not self.trigger_map:
            def default_flow_fn(**kwargs):
                active_input_port = kwargs['active_input_port']
                c = kwargs.get('c', {})
                messages_output = kwargs['messages_output']

                # Get only the ports that aren't string-based
                input_port_keys = [
                    key for key in self.flow_controller.flow_port_map.keys()
                    if key != 'messages_output' and not isinstance(self.input_map[key][1], str)
                ]
                
                input_name_payload_dict = c.setdefault('input_name_payload_dict', {})
                input_name_payload_dict[active_input_port.name] = active_input_port.payload

                if all(key in input_name_payload_dict for key in input_port_keys):
                    msg_payload_list = []
                    for key in self.input_map.keys():
                        if isinstance(self.input_map[key][1], str):
                            msg_payload_list.append(self.preset_messages[key])
                        else:
                            payload = input_name_payload_dict[key]
                            # Overriding role from the input map for port payload conversions.
                            converted = to_message_payload(
                                payload,
                                self.payload_message_mapping,
                                expected_type=self.flow_controller.flow_port_map[key].payload_type,
                                role=self.input_map[key][0]  # specified role from input_map
                            )
                            if isinstance(converted, list):
                                msg_payload_list.extend(converted)
                            else:
                                msg_payload_list.append(converted)
                                
                    input_name_payload_dict.clear()
                    messages_output.emit(msg_payload_list)
            
            flow_controller_kwargs['user_flow_fn'] = default_flow_fn

        self.flow_controller = FlowController(containing_element=self, **flow_controller_kwargs)
        self.ports = self.flow_controller.ports

    def _flow_map_setup(self, input_map):
        flow_map = {'input': {}, 'output': {'messages_output': list[MessagePayload]}}
        for key, (msg_type, payload_type) in input_map.items():
            if (isinstance(payload_type, type) and issubclass(payload_type, Payload)) or \
            (hasattr(payload_type, '__origin__') and issubclass(payload_type.__origin__, list)):
                flow_map['input'][key] = payload_type
            elif isinstance(payload_type, str):
                self.preset_messages[key] = MessagePayload(content=payload_type, role=msg_type)
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
                        self.preset_messages[key] = MessagePayload(content=msg_string, role=msg_type)
                    if key not in self.input_map:
                        self.input_map[key] = (msg_type, msg_string)
                else:
                    raise ValueError(f"Invalid value for key '{key}': {ports_or_string}")
        
        return connected_flow_map