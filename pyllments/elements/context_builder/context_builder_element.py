import param
from jinja2 import meta
import jinja2

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, Ports
from pyllments.base.element_base import Element
from .to_message import to_message_payload, payload_message_mapping


class ContextBuilder(Element):
    """
    The ContextBuilder aggregates messages from multiple input ports and emits them
    as a single list of messages, handling constants, templates, and port persistence.
    """
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping the port name, a constant name, or a template name to their corresponding
        instances. 
        - Ports: Input ports with 'role' and 'payload_type' keys.
            Optional 'persist' flag (defaults to False) - determines if payload persists in flow controller.
            Optional 'callback' function to transform the payload when it is received by the port.
                e.g. 'callback': lambda payload: do_something(payload.model.content)
        - Constants: Keys ending with '_constant' with 'role' and 'message' keys.
        - Templates: Keys ending with '_template' with 'role' and 'template' keys.
        Example:
        input_map = {
            'port_a': {'role': 'user', 'persist': True, 'ports': [el1.ports.output['some_output']]},
            'port_b': {'role': 'assistant', 'payload_type': list[MessagePayload]}, 
            'user_constant': {'role': 'user', 'message': "This text will be a user message"}, 
            'system_template': {'role': 'system', 'template': "{{ port_a }}  --  {{ port_b }}"}
        }
        """)
        
    emit_order = param.List(default=[], doc="""
        A list of port names in the order of the messages to be emitted.
        Use when neither the trigger_map nor build_fn are provided.
        Waits until all payloads are available.
        """)

    trigger_map = param.Dict(default={}, doc="""
        A dictionary mapping between a port alias and a list of ports and messages that sets the key 
        port as the trigger to build messages in the order of the provided list(value).
        """)
    
    build_fn = param.Callable(default=None, doc="""
        A more advanced alternative to the trigger_map.
        A function used to provide conditional control to the context creation process.
        """)

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An input port to connect to the flow controller's messages_output port.""")
    
    payload_message_mapping = param.Dict(default=payload_message_mapping, doc="""
        Mapping between payload types and message conversion functions.""")

    ports = param.ClassSelector(class_=Ports, doc="""
        The ports object for the context builder.""")

    def __init__(self, **params):
        # Initialize storage collections
        self._initialize_storage()
        
        # Process input_map if provided
        if 'input_map' in params:
            self._process_input_map(params['input_map'])
        
        super().__init__(**params)
        
        # Set up flow controller and connect ports
        self._setup_flow_controller()
        
        if self.outgoing_input_port:
            self.ports.messages_output > self.outgoing_input_port

    def _initialize_storage(self):
        """Initialize all storage collections as instance variables."""
        self.callbacks = {}        # port_name -> callback function
        self.port_types = {}       # name -> 'regular', 'template', or 'constant'
        self.port_roles = {}       # name -> role string
        self.required_ports = []   # list of required regular port names
        self.constants = {}        # constant_name -> MessagePayload
        self.templates = {}        # template_name -> {role, template}
        self.template_storage = {} # template_name -> {port_name: payload}
        self.template_dependencies = {}  # template_name -> [dependency names]

    def _process_input_map(self, input_map):
        """Process input map entries and populate storage collections."""
        if not input_map:
            return
            
        for name, config in input_map.items():
            if isinstance(config, dict) and name != 'output':
                self._register_entry(name, config)

    def _register_entry(self, name, config):
        """Register an input map entry based on its type."""
        # Determine entry type based on name suffix
        if name.endswith('_constant'):
            self._register_constant(name, config)
        elif name.endswith('_template'):
            self._register_template(name, config)
        else:
            self._register_port(name, config)

    def _register_constant(self, name, config):
        """Register a constant message."""
        role = config.get('role', 'user')
        message = config.get('message', '')
        
        self.port_types[name] = 'constant'
        self.port_roles[name] = role
        self.constants[name] = MessagePayload(content=message, role=role)

    def _register_template(self, name, config):
        """Register a template and its dependencies."""
        role = config.get('role', 'system')
        template_str = config.get('template', '')
        
        self.port_types[name] = 'template'
        self.port_roles[name] = role
        self.templates[name] = {'role': role, 'template': template_str}
        self.template_storage[name] = {}
        
        # Parse template dependencies
        env = jinja2.Environment()
        parsed = env.parse(template_str)
        self.template_dependencies[name] = list(meta.find_undeclared_variables(parsed))

    def _register_port(self, name, config):
        """Register a regular port configuration."""
        self.port_types[name] = 'regular'
        self.port_roles[name] = config.get('role', 'user')
        
        if name != 'messages_output' and name not in self.required_ports:
            self.required_ports.append(name)
            
        if 'callback' in config:
            self.callbacks[name] = config['callback']

    def _setup_flow_controller(self):
        """Set up the flow controller with the configured flow map."""
        # Create flow map and flow function
        flow_map = self._create_flow_map()
        flow_fn = self._create_flow_function()
        
        # Create flow controller
        self.flow_controller = FlowController(
            containing_element=self,
            flow_map=flow_map,
            flow_fn=flow_fn
        )
        
        # Use flow controller's ports as our ports
        self.ports = self.flow_controller.ports

    def _create_flow_map(self):
        """Create the flow map for the flow controller."""
        flow_map = {
            'input': {},
            'output': {'messages_output': {"payload_type": list[MessagePayload]}}
        }

        # Add only regular port configurations
        for name, config in self.input_map.items():
            if self.port_types.get(name) == 'regular' and 'ports' in config:
                port_config = config.copy()
                if 'payload_type' not in port_config:
                    port_config['payload_type'] = MessagePayload
                
                # Ensure persist flag is properly set
                port_config['persist'] = config.get('persist', False)
                
                flow_map['input'][name] = port_config
        
        return flow_map

    def _create_flow_function(self):
        """Create the flow function for the flow controller."""
        def flow_fn(**kwargs):
            active_port = kwargs['active_input_port']
            messages_output = kwargs['messages_output']
            port_name = active_port.name

            # Apply callback if exists
            if port_name in self.callbacks and active_port.payload is not None:
                active_port.payload = self.callbacks[port_name](active_port.payload)

            # Update template storage
            if active_port.payload is not None:
                self._update_template_storage(port_name, active_port.payload)
            
            # Process messages using configured strategy
            self._process_messages(kwargs, messages_output, port_name)
            
            return None
        
        return flow_fn

    def _update_template_storage(self, port_name, payload):
        """Update template storage for templates that depend on this port."""
        for template_name, deps in self.template_dependencies.items():
            if port_name in deps:
                if template_name not in self.template_storage:
                    self.template_storage[template_name] = {}
                self.template_storage[template_name][port_name] = payload

    def _process_messages(self, kwargs, messages_output, port_name):
        """Process messages using the appropriate strategy."""
        # Get message ordering based on strategy
        order = self._get_message_order(kwargs, port_name)
        
        # Process messages if all required ports are available
        if order and self._has_required_dependencies(order):
            messages = []
            
            # Get messages based on ordering
            for name in order:
                msg = self._get_message(name)
                if msg:
                    if isinstance(msg, list):
                        messages.extend(msg)
                    else:
                        messages.append(msg)
            
            # Emit messages if available
            if messages:
                messages_output.emit(messages)

    def _get_message_order(self, kwargs, port_name):
        """Get the message ordering based on configured strategy."""
        if self.build_fn:
            return self.build_fn(**kwargs)
        elif self.trigger_map and port_name in self.trigger_map:
            return self.trigger_map[port_name]
        elif self.emit_order:
            return self.emit_order
        return None

    def _has_required_dependencies(self, order):
        """Check if all required dependencies are available."""
        for name in order:
            if self.port_types.get(name) == 'regular':
                # Check regular port
                port = self.flow_controller.flow_port_map.get(name)
                if not port or not port.payload:
                    return False
            elif self.port_types.get(name) == 'template':
                # Check template dependencies
                deps = self.template_dependencies.get(name, [])
                for dep in deps:
                    port = self.flow_controller.flow_port_map.get(dep)
                    if not port or not port.payload:
                        return False
        return True

    def _get_message(self, name):
        """Get a message for a given name based on its type."""
        port_type = self.port_types.get(name)
        
        if port_type == 'constant':
            return self.constants.get(name)
        
        elif port_type == 'template':
            template_data = self.templates.get(name)
            if template_data:
                return self._process_template(template_data, name)
        
        elif port_type == 'regular':
            port = self.flow_controller.flow_port_map.get(name)
            if port and port.payload is not None:
                role = self.port_roles.get(name)
                return self._convert_payload_to_message(name, port.payload, role)
        
        return None

    def _process_template(self, template_data, template_name):
        """Process a template using its dependencies."""
        role = template_data.get('role', 'system')
        template_str = template_data.get('template', '')
        
        # Get dependencies for this template
        deps = self.template_dependencies.get(template_name, [])
        
        # Build template context
        context = {}
        for dep_name in deps:
            port = self.flow_controller.flow_port_map.get(dep_name)
            if not port or not port.payload:
                return None
                
            msg = self._convert_payload_to_message(dep_name, port.payload, self.port_roles.get(dep_name))
            if not msg:
                return None
                
            context[dep_name] = msg.model.content if hasattr(msg, 'model') else str(msg)
        
        # Render template
        try:
            env = jinja2.Environment(undefined=jinja2.StrictUndefined)
            rendered = env.from_string(template_str).render(**context)
            return MessagePayload(content=rendered, role=role)
        except Exception as e:
            return MessagePayload(content=f"Error rendering template: {str(e)}", role=role)

    def _convert_payload_to_message(self, name, payload, role=None):
        """Convert a payload to a MessagePayload with the specified role."""
        if payload is None:
            return None
            
        # Get payload type for conversion
        if name in self.flow_controller.flow_port_map:
            port_type = self.flow_controller.flow_port_map[name].payload_type
        else:
            port_type = MessagePayload
        
        try:
            return to_message_payload(
                payload,
                self.payload_message_mapping,
                expected_type=port_type,
                role=role
            )
        except Exception as e:
            return MessagePayload(
                content=f"Error converting payload: {str(e)}",
                role=role or "system"
            )