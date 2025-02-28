import param
import jinja2

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, Ports
from pyllments.base.element_base import Element
from .to_message import to_message_payload, payload_message_mapping


class ContextBuilder(Element):
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping the port name, a constant name, or a template name to their corresponding
        instances. 
        - Ports: Input ports with 'role' and 'payload_type' keys. Optional 'persist' flag (defaults to False).
        - Constants: Keys ending with '_constant' with 'role' and 'message' keys.
        - Templates: Keys ending with '_template' with 'role' and 'template' keys.
        
        Example:
        input_map = {
            'port_a': {'role': 'user', 'payload_type': MessagePayload, 'persist': True},
            'port_b': {'role': 'assistant', 'payload_type': list[MessagePayload]}, 
            'user_constant': {'role': 'user', 'message': "This text will be a user message"}, 
            'system_template': {'role': 'system', 'template': "{{ port_a }}  --  {{ port_b }}"}
        }
        """)
        
    connected_input_map = param.Dict(default={}, doc="""
        A dictionary mapping the port name, a constant name, or a template name to their corresponding
        instances. Similar to input_map but for connecting to existing ports.
        - Ports: Input ports with 'role' and 'ports' keys (list of output ports to connect to).
        - Constants: Keys ending with '_constant' with 'role' and 'message' keys.
        - Templates: Keys ending with '_template' with 'role' and 'template' keys.
        
        Example:
        connected_input_map = {
            'port_a': {'role': 'user', 'ports': [el1.ports.some_output]},
            'port_b': {'role': 'assistant', 'persist': True, 'ports': [el2.ports.some_output]},
            'system_constant': {'role': 'system', 'message': "This text will be a sys message"},
            'system_template': {'role': 'system', 'template': "{{ port_a }}  --  {{ port_b }}"}
        }
        """)

    emit_order = param.List(default=[], doc="""
        A list of msg/port names in the order of the messages to be emitted.
        Use when neither the trigger_map nor build_fn are provided.
        Waits until all payloads are available.
        e.g.
        emit_order = ['port_a', 'port_b', 'system_constant', 'system_template']
        """)

    trigger_map = param.Dict(default={}, doc="""
        A dictionary mapping between a port alias and a list of ports and messages that sets the key 
        port as the trigger to exhaustively build messages in the order of the provided list(value).
        e.g.
        trigger_map = {
            'port_a': ['port_a', 'port_b', 'system_constant'],
            'port_b': ['port_b', 'system_constant']
        }
        """)
    
    build_fn = param.Callable(default=None, doc="""
        A more advanced alternative to the build_map.
        A function used to provide conditional control to the context creation process.
        e.g.
        def build_fn(port_a, port_b, system_constant, active_input_port, c):
            if active_input_port == port_a:
                return [port_a, port_b, system_constant]
            else:
                return [port_b, system_constant]
        """)

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An optional input port to connect to the flow controller's output upon initialization.
        Connects to the messages_output port of the flow controller.""")
    
    payload_message_mapping = param.Dict(default=payload_message_mapping, doc="""
        Mapping between payload types and message conversion functions.""")

    ports = param.ClassSelector(class_=Ports, doc="""
        The ports object for the context builder from the flow controller.""")

    def __init__(self, **params):
        super().__init__(**params)
        
        # Create lookup tables for all port information
        self.port_types = {}      # port_name -> 'regular', 'template', 'constant'
        self.port_roles = {}      # port_name -> role
        self.port_persist = []    # List of port names that should persist
        self.required_ports = []  # list of required regular port names
        self.constants = {}       # constant_name -> MessagePayload
        self.templates = {}       # template_name -> template_data
        
        # Initialize all lookup tables
        self._initialize_lookups()
        
        # Set up flow controller
        self._flow_controller_setup()
        self.ports = self.flow_controller.ports
        
        if self.outgoing_input_port:
            self.ports.messages_output > self.outgoing_input_port

    def _flow_controller_setup(self):
        """Set up the flow controller with the configured inputs and outputs."""
        if not (self.input_map or self.connected_input_map):
            raise ValueError("At least one of input_map or connected_input_map must be provided.")
        
        flow_controller_kwargs = {}
        
        # Setup basic flow maps
        flow_map = self._flow_map_setup(self.input_map)
        flow_controller_kwargs['flow_map'] = flow_map
        
        if self.connected_input_map:
            connected_flow_map = self._connected_flow_map_setup(self.connected_input_map)
            flow_controller_kwargs['connected_flow_map'] = connected_flow_map

        flow_controller_kwargs['flow_fn'] = self._create_context_flow_fn()
        self.flow_controller = FlowController(containing_element=self, **flow_controller_kwargs)
        self.ports = self.flow_controller.ports

    def _create_context_flow_fn(self):
        """Create the flow function for the flow controller."""
        def context_flow_fn(**kwargs):
            active_input_port = kwargs['active_input_port']
            c = kwargs['c']  # This should always be provided by FlowController
            messages_output = kwargs['messages_output']
            port_name = active_input_port.name

            if 'input_name_payload_dict' not in c:
                c['input_name_payload_dict'] = {}
            
            if active_input_port.payload is not None:
                c['input_name_payload_dict'][port_name] = active_input_port.payload
            
            should_persist = port_name in self.port_persist
            used_ports = set()
            processing_successful = False
            result_message_keys = []
            
            # Try each processing strategy in order of priority
            processing_result = self._try_processing_strategies(
                kwargs, c['input_name_payload_dict'], messages_output, port_name
            )
            
            if processing_result:
                processing_successful = True
                result_message_keys = processing_result['keys']
                used_ports = processing_result['used_ports']
            
            # Clean up non-persisted ports
            if processing_successful:
                for p_name in list(c['input_name_payload_dict'].keys()):
                    if (p_name not in self.port_persist and 
                        p_name != port_name and
                        p_name not in used_ports and
                        p_name not in result_message_keys):
                        c['input_name_payload_dict'].pop(p_name, None)
            elif not should_persist:
                c['input_name_payload_dict'].pop(port_name, None)
                
            return None
        
        return context_flow_fn

    def _try_processing_strategies(self, kwargs, input_name_payload_dict, messages_output, port_name):
        """Try each processing strategy in order of priority.
        
        Returns a dict with 'keys' and 'used_ports' if successful, None otherwise.
        """
        # Helper function to check if all required regular ports are available for a given order
        def has_required_ports(order):
            for p in order:
                if self.port_types.get(p) == 'regular' and p not in input_name_payload_dict:
                    return False
            return True
        
        # Strategy 1: Use build_fn if available
        if self.build_fn:
            # Prepare kwargs for build_fn
            build_fn_kwargs = kwargs.copy()
            build_fn_kwargs['input_name_payload_dict'] = input_name_payload_dict.copy()
            
            # Get the ordering from the user's build_fn
            result_order = self.build_fn(**build_fn_kwargs)
            
            if result_order and has_required_ports(result_order):
                result = self._process_with_order(result_order, input_name_payload_dict, messages_output)
                if result:
                    return result
        
        # Strategy 2: Use trigger_map if applicable
        if self.trigger_map and port_name in self.trigger_map:
            result_order = self.trigger_map[port_name]
            if has_required_ports(result_order):
                result = self._process_with_order(result_order, input_name_payload_dict, messages_output)
                if result:
                    return result
        
        # Strategy 3: Use emit_order if all required ports are available
        if self.emit_order and has_required_ports(self.emit_order):
            result = self._process_with_order(self.emit_order, input_name_payload_dict, messages_output)
            if result:
                return result
        
        # Strategy 4: Default behavior - use all available ports in order of definition
        if all(port in input_name_payload_dict for port in self.required_ports) and self.required_ports:
            ordered_keys = list(self.connected_input_map.keys() if self.connected_input_map else self.input_map.keys())
            result = self._process_with_order(ordered_keys, input_name_payload_dict, messages_output)
            if result:
                return result
        
        return None

    def _process_with_order(self, order, input_name_payload_dict, messages_output):
        """Process messages using the given order.
        
        Returns a dict with 'keys' and 'used_ports' if successful, None otherwise.
        """
        msg_payload_list = []
        used_ports = set()
        
        # Process each key in the order
        for key in order:
            # Track regular ports for cleanup
            if self.port_types.get(key) == 'regular':
                used_ports.add(key)
                
            # Get and add the message to the payload list
            message = self._get_message(key, input_name_payload_dict)
            if message:
                if isinstance(message, list):
                    msg_payload_list.extend(message)
                else:
                    msg_payload_list.append(message)
        
        # Only emit if we have messages to send
        if msg_payload_list:
            messages_output.emit(msg_payload_list)
            return {
                'keys': order,
                'used_ports': used_ports
            }
        
        return None

    def _get_message(self, key, input_name_payload_dict):
        """Get a message for a key using direct lookups."""
        port_type = self.port_types.get(key)
        
        if port_type == 'template':
            # Process template
            template_data = self.templates.get(key)
            if template_data:
                return self._process_template(template_data, input_name_payload_dict)
        
        elif port_type == 'constant':
            # Return constant
            return self.constants.get(key)
        
        elif port_type == 'regular' and key in input_name_payload_dict:
            # Process port payload
            payload = input_name_payload_dict[key]
            role = self.port_roles.get(key)
            return self._convert_payload_to_message(key, payload, role)
        
        return None

    def _convert_payload_to_message(self, port_name, payload, role=None):
        """Convert a payload to a MessagePayload with the specified role."""
        if payload is None:
            return None
            
        port_type = self.flow_controller.flow_port_map[port_name].payload_type
        
        try:
            converted = to_message_payload(
                payload,
                self.payload_message_mapping,
                expected_type=port_type,
                role=role
            )
            return converted
        except (ValueError, AttributeError) as e:
            return MessagePayload(
                content=f"Error converting payload: {str(e)}",
                role=role or "system"
            )

    def _flow_map_setup(self, input_map):
        """Set up the flow map based on the input_map configuration."""
        flow_map = {'input': {}, 'output': {'messages_output': list[MessagePayload]}}
        
        # Add all regular ports from the input_map
        for key, config in input_map.items():
            if key != 'output' and not key.endswith('_constant') and not key.endswith('_template'):
                payload_type = config.get('payload_type')
                if payload_type:
                    flow_map['input'][key] = payload_type
        
        return flow_map

    def _connected_flow_map_setup(self, connected_input_map):
        """Set up the connected flow map based on the connected_input_map configuration."""
        connected_flow_map = {'input': {}, 'output': {}}
        
        for key, value in connected_input_map.items():
            if key == 'output':
                # Handle output connections
                for out_key, ports in value.items():
                    if isinstance(ports, (list, tuple)):
                        connected_flow_map['output'][out_key] = ports
                    elif isinstance(ports, InputPort):
                        connected_flow_map['output'][out_key] = [ports]
                    else:
                        raise ValueError(f"Invalid value for output key '{out_key}': {ports}")
            elif self.port_types.get(key) == 'constant' or self.port_types.get(key) == 'template':
                # Constants and templates are already handled in _initialize_lookups
                pass
            else:
                # Handle port connections
                ports = value.get('ports', [])
                ports_list = ports if isinstance(ports, (list, tuple)) else [ports]
                
                if ports_list:
                    connected_flow_map['input'][key] = ports_list
                    if key not in self.input_map:
                        payload_type = ports_list[0].payload_type
                        self.input_map[key] = {
                            'role': self.port_roles.get(key, 'user'), 
                            'payload_type': payload_type, 
                            'persist': key in self.port_persist
                        }
        
        return connected_flow_map
        
    def _process_template(self, template_data, input_name_payload_dict):
        """Process a Jinja2 template with payload content from the specified ports."""
        role = template_data.get('role', 'system')
        template_str = template_data.get('template', '')
        
        # Use a special Jinja2 environment that returns an empty string for undefined variables
        env = jinja2.Environment(undefined=jinja2.Undefined)
        template_obj = env.from_string(template_str)
        
        # Create a context with port values
        template_context = {}
        for port_name, payload in input_name_payload_dict.items():
            if payload is not None and self.port_types.get(port_name) == 'regular':
                converted = self._convert_payload_to_message(
                    port_name, 
                    payload, 
                    self.port_roles.get(port_name)
                )
                
                if isinstance(converted, list):
                    # For lists, join the content of all messages
                    template_context[port_name] = '\n'.join([msg.model.content for msg in converted if hasattr(msg, 'model')])
                elif converted and hasattr(converted, 'model'):
                    template_context[port_name] = converted.model.content
        
        try:
            rendered_content = template_obj.render(**template_context)
            return MessagePayload(content=rendered_content, role=role)
        except Exception as e:
            # Handle template rendering errors
            error_msg = f"Error rendering template: {str(e)}"
            return MessagePayload(content=error_msg, role=role)

    def _build_message_list(self, items, input_name_payload_dict, kwargs=None):
        """Build a message list from a list of items (ports or strings)."""
        msg_payload_list = []
        for item in items:
            if isinstance(item, str):
                # Get the message based on the item type
                message = self._get_message(item, input_name_payload_dict)
                if message:
                    if isinstance(message, list):
                        msg_payload_list.extend(message)
                    else:
                        msg_payload_list.append(message)
            else:
                # Handle port objects (assuming they are flow ports)
                if not hasattr(item, 'payload'):
                    raise TypeError(f"Expected flow port object or string, got {type(item)}")
                    
                payload = item.payload
                if payload is None:
                    continue
                
                # Convert payload to message
                port_name = item.name
                role = self.port_roles.get(port_name)
                converted = self._convert_payload_to_message(port_name, payload, role)
                
                if isinstance(converted, list):
                    msg_payload_list.extend(converted)
                elif converted:
                    msg_payload_list.append(converted)
        
        return msg_payload_list

    def _initialize_lookups(self):
        """Initialize all lookup tables from input maps."""
        # Process both input maps
        for input_map_name in ['input_map', 'connected_input_map']:
            input_map = getattr(self, input_map_name, {})
            if not input_map:
                continue
                
            for key, config in input_map.items():
                if not isinstance(config, dict) or key == 'output':
                    continue
                    
                # Skip if already processed (from input_map)
                if key in self.port_types and input_map_name == 'connected_input_map':
                    continue
                
                self._register_entry(key, config, input_map_name)
    
    def _register_entry(self, key, config, source_map):
        """Register an entry in the lookup tables based on its type."""
        # Determine entry type based on key suffix
        entry_type = 'regular'  # Default
        if key.endswith('_constant'):
            entry_type = 'constant'
        elif key.endswith('_template'):
            entry_type = 'template'
            
        # Set common properties
        self.port_types[key] = entry_type
        
        # Handle type-specific properties
        if entry_type == 'constant':
            role = config.get('role', 'user')
            self.port_roles[key] = role
            if key not in self.port_persist:
                self.port_persist.append(key)  # Constants always persist
            self.constants[key] = MessagePayload(
                content=config.get('message', ''),
                role=role
            )
        elif entry_type == 'template':
            role = config.get('role', 'system')
            self.port_roles[key] = role
            if key not in self.port_persist:
                self.port_persist.append(key)  # Templates always persist
            self.templates[key] = {
                'role': role,
                'template': config.get('template', '')
            }
        else:  # Regular port
            self.port_roles[key] = config.get('role', 'user')
            if config.get('persist', False) and key not in self.port_persist:
                self.port_persist.append(key)
            
            # Add to required ports if it's a regular port (not output)
            if key != 'messages_output' and key not in self.required_ports:
                self.required_ports.append(key)