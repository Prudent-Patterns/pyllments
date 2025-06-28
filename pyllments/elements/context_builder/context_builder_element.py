import param
from jinja2 import meta
import jinja2
import asyncio
from loguru import logger
import time

from pyllments.elements.flow_control import FlowController
from pyllments.payloads.message import MessagePayload
from pyllments.ports import InputPort, Ports
from pyllments.base.element_base import Element
from .to_message import to_message_payload, payload_message_mapping

# Add a unique marker for invalid dependency sets
_INVALID_DEPENDENCY_MARKER = frozenset(['__INVALID_DEPENDENCY__'])

class ContextBuilderElement(Element):
    """
    Aggregates messages from various sources (input ports, constants, templates)
    and emits them as a single, ordered list of MessagePayloads.

    Handles payload conversion, port persistence, optional items, and complex
    dependency checks to ensure messages are emitted only when specified
    conditions are met. Uses a sequential processing model; only one trigger
    event is processed at a time.

    Uses conversion functions (see `payload_message_mapping`) to transform
    incoming payloads into the standard `MessagePayload` format.

    Role Assignment:
    - Ports without explicit 'role': Preserves original message roles (no mutation)
    - Ports with explicit 'role': Overrides all messages with specified role
    - Constants/Templates: Use specified role or defaults ('user'/'system')

    Key Concepts:
    - Input Sources: Defined via `input_map`. Can be:
        - Regular Ports: Receive payloads dynamically. Can be marked `persist=True`.
        - Constants: Fixed messages (name ends with '_constant').
        - Templates: Messages rendered using Jinja2 syntax with port payloads
          as variables (name ends with '_template'). Template variables
          implicitly create dependencies.
    - Emission Control: Defined by `trigger_map`, `emit_order`, or `build_fn`.
      Determines the sequence of items to include in the output list.
    - Optional Items: Items listed in `trigger_map` or `emit_order` wrapped
      in square brackets (e.g., `[history]`) are optional. They are included
      if available and ready, but their absence doesn't block emission.
    - Dependencies:
        - Trigger/Order: All non-optional items in the active trigger list
          must satisfy their requirements for emission to occur.
        - Explicit (`depends_on`): Any item (port, constant, template) can
          have a `depends_on` list in its `input_map` config. This item
          will *only* be included (even if optional in the order) if all
          ports listed in its `depends_on` clause have payloads.
        - Template Variables: Templates implicitly depend on non-optional
          variables (e.g., `{{ user_msg }}`). Optional variables (`{{ [opt_var] }}`)
          are allowed to be missing during rendering.

    Example:
    ```python
    context_builder = ContextBuilderElement(
        input_map={
            'system_prompt_constant': { # A fixed system message
                'role': 'system', 'message': "You are helpful."
            },
            'history': { # A regular port for chat history
                'payload_type': list[MessagePayload],
                'ports': [history_handler.ports.output['history_output']],
                'persist': True # Keep history available
            },
            'tools': { # A regular port for available tools
                'role': 'system', 'ports': [tools_provider.ports.output['tools_output']]
            },
            'history_header_constant': { # Constant only shown if history exists
                'role': 'system', 'message': "Chat History:",
                'depends_on': 'history'
            },
            'tools_header_template': { # Template only shown if tools exist
                 'role': 'system', 'template': "Available Tools: {{ tools }}",
                 # 'depends_on': 'tools' # Implicit via template variable
            },
            'user_query': { # The user's latest message
                'role': 'user', 'ports': [chat_ui.ports.output['message_output']]
            }
        },
        trigger_map={
            # When user sends a query, build the full context
            'user_query': [
                'system_prompt_constant',
                '[history_header_constant]', # Optional header (depends on history)
                '[history]',                 # Optional history messages
                '[tools_header_template]',   # Optional tools (implicitly depends on tools port)
                '[tools]',                   # Optional tools content
                'user_query'                 # Required user query
            ]
        }
    )
    ```
    """
    # ---- Configuration Parameters ----
    
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping the port name, a constant name, or a template name to their corresponding
        instances. 
        - Ports: Input ports with 'role' and 'payload_type' keys.
            Optional 'persist' flag (defaults to False) - determines if payload persists in flow controller.
            Optional 'callback' function to transform the payload when it is received by the port.
                e.g. 'callback': lambda payload: do_something(payload.model.content)
            Optional 'depends_on' to specify dependencies on other ports.
        - Constants: Keys ending with '_constant' with 'role' and 'message' keys.
            Optional 'depends_on' to only include the constant when specified ports have data.
        - Templates: Keys ending with '_template' with 'role' and 'template' keys. (defined after their ports)
            Optional 'depends_on' for additional dependencies beyond the template variables.
        
        The 'depends_on' field can be a string (single dependency) or a list of strings (multiple dependencies).
        This ensures the item is only included when all its dependencies have payloads.
        
        Example:
        input_map = {
            'port_a': {'role': 'user', 'persist': True, 'ports': [el1.ports.output['some_output']]},
            'port_b': {'role': 'assistant', 'payload_type': list[MessagePayload]}, 
            'user_constant': {'role': 'user', 'message': "This text will be a user message"}, 
            'system_template': {'role': 'system', 'template': "{{ port_a }}  --  {{ port_b }}"},
            'history_header': {'role': 'system', 'message': "Chat history:", 'depends_on': 'history'}
        }
        """)
        
    emit_order = param.List(default=[], doc="""
        A list of port names in the order of the messages to be emitted.
        Use when neither the trigger_map nor build_fn are provided.
        Waits until all required payloads are available.
        
        Optional items can be marked with square brackets: ['required_item', '[optional_item]']
        Optional items will be included if available, but won't block processing if missing.
        """)

    trigger_map = param.Dict(default={}, doc="""
        A dictionary mapping between a port alias and a list of ports and messages that sets the key 
        port as the trigger to build messages in the order of the provided list(value).
        
        Optional items can be marked with square brackets: ['required_item', '[optional_item]']
        Optional items will be included if available, but won't block processing if missing.
        
        Example:
        trigger_map = {
            'query': ['system_msg', '[history]', 'query'],  # history is optional 
            'tool_response': ['system_msg', 'query', 'tool_response']
        }
        """)
    
    build_fn = param.Callable(default=None, doc="""
        A more advanced alternative to the trigger_map.
        A function used to provide conditional control to the context creation process.
        """)

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")

    outgoing_input_ports = param.List(default=[], item_type=InputPort, doc="""
        A list of input ports to connect to the flow controller's messages_output port.""")
    
    payload_message_mapping = param.Dict(default=payload_message_mapping, doc="""
        Mapping between payload types and message conversion functions.""")

    ports = param.ClassSelector(class_=Ports, doc="""
        The ports object for the context builder.""")

    # Internal state flag to prevent concurrent processing
    _is_processing = param.Boolean(False, precedence=-1, doc="Internal flag to indicate if a flow is currently being processed.")

    # ---- Initialization ----
    
    def __init__(self, **params):
        # Initialize storage collections
        self._initialize_storage()
        
        self._pending_trigger = None
        
        self._process_input_map(params['input_map'])
        
        super().__init__(**params)
        
        # Set up flow controller and connect ports
        self._setup_flow_controller()
        
        if self.outgoing_input_ports:
            for port in self.outgoing_input_ports:
                self.ports.messages_output > port
            
        # Pre-compute dependencies after all items are registered
        self._precompute_all_dependencies()

    def _initialize_storage(self):
        """Initialize all storage collections as instance variables."""
        self.callbacks = {}        # port_name -> callback function
        self.port_types = {}       # name -> 'regular', 'template', or 'constant'
        self.port_roles = {}       # name -> role string
        self.required_ports = []   # list of required regular port names
        self.constants = {}        # constant_name -> MessagePayload
        self.templates = {}        # template_name -> {role, template}
        self.template_storage = {} # template_name -> {port_name: payload}
        self.template_dependencies = {}  # template_name -> [dependency names] from template vars
        self.dependencies = {}     # name -> list of explicit dependency specs (from 'depends_on')
        self._is_processing = False # Initialize processing lock
        self._full_dependency_sets = {} # Cache for pre-computed full dependency sets {item_name: frozenset(deps) or _INVALID_DEPENDENCY_MARKER}

    # ---- Input Map Processing ----
    
    def _process_input_map(self, input_map):
        """Process input map entries and populate storage collections."""
        if not input_map:
            return
            
        for name, config in input_map.items():
            if isinstance(config, dict) and name != 'output':
                self._register_entry(name, config)

    def _register_entry(self, name, config):
        """Register an input map entry based on its type."""
        # Check for dependencies
        if 'depends_on' in config:
            depends_on = config['depends_on']
            if isinstance(depends_on, str):
                self.dependencies[name] = [depends_on]
            elif isinstance(depends_on, list):
                self.dependencies[name] = depends_on
        
        # Determine entry type based on name suffix
        if name.endswith('_constant'):
            self._register_constant(name, config)
        elif name.endswith('_template'):
            self._register_template(name, config)
        else:
            self._register_port(name, config)

    def _register_constant(self, name, config):
        """Register a constant message."""
        role = config.get('role', 'user')  # Default to 'user' for new messages
        message = config.get('message', '')
        
        self.port_types[name] = 'constant'
        self.port_roles[name] = role
        self.constants[name] = MessagePayload(content=message, role=role)

    def _register_template(self, name, config):
        """Register a template and its dependencies."""
        role = config.get('role', 'system')  # Default to 'system' for new template messages
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
        # For ports, only store role if explicitly specified (to override received messages)
        # If no role is specified, received messages keep their original roles
        if 'role' in config:
            self.port_roles[name] = config['role']
        else:
            self.port_roles[name] = None  # No role override for received messages
        
        if name != 'messages_output' and name not in self.required_ports:
            self.required_ports.append(name)
            
        if 'callback' in config:
            self.callbacks[name] = config['callback']

    # ---- Flow Controller Setup ----
    
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
            if self.port_types.get(name) == 'regular':
                port_config = config.copy()
                if ('payload_type' not in port_config) and ('ports' not in port_config):
                    raise ValueError(f"Payload type or ports not specified for port {name}")
                
                # Always persist ports in the flow; we will clear non-persistent ports manually after emit
                port_config['persist'] = True
                
                flow_map['input'][name] = port_config
        
        return flow_map

    def _create_flow_function(self):
        """Create the flow function for the flow controller."""
        async def flow_fn(**kwargs):
            active_port = kwargs['active_input_port']
            messages_output = kwargs['messages_output']
            active_name = active_port.name
            total_required = len(self.required_ports)
            ready = [
                name for name in self.required_ports
                if getattr(self.flow_controller.flow_port_map.get(name), 'payload', None) is not None
            ]
            missing = [name for name in self.required_ports if name not in ready]

            self.logger.debug(
                f"Received payload on '{active_name}'. Progress: {len(ready)}/{total_required} ready; Missing: {missing}"
            )

            if active_name in self.callbacks and active_port.payload is not None:
                active_port.payload = self.callbacks[active_name](active_port.payload)
            if active_port.payload is not None:
                self._update_template_storage(active_name, active_port.payload)

            # Determine if this arrival should start or feed the pending trigger
            if self.build_fn:
                triggerable = True
            elif self.trigger_map:
                triggerable = active_name in self.trigger_map
            elif self.emit_order:
                real_emit = [self._get_real_name(n) for n in self.emit_order]
                triggerable = active_name in real_emit
            else:
                triggerable = False

            if not self._is_processing:
                if not triggerable:
                    self.logger.trace(f"Ignoring non-trigger port {active_name}")
                    return None
                # Begin a new trigger flow
                self._is_processing = True
                self._pending_trigger = active_name
                self.logger.debug(f"Acquired lock for trigger {active_name}")
            else:
                self.logger.debug(f"Received dependency {active_name} for trigger {self._pending_trigger}")

            # Determine order and process messages for the pending trigger
            order = self._get_message_order(kwargs, self._pending_trigger)
            # Instrumentation: measure message processing time
            start_time = time.perf_counter()
            emitted = await self._process_messages(kwargs, messages_output, self._pending_trigger)
            elapsed = time.perf_counter() - start_time
            self.logger.debug(f"ContextBuilderElement: message processing for trigger '{self._pending_trigger}' took {elapsed:.4f} seconds")
            # Release lock and clear consumed payloads if we fulfilled and emitted
            if emitted:
                # Clear only regular ports that are not marked persist in the input_map
                for name in order:
                    real_name = self._get_real_name(name)
                    if self.port_types.get(real_name) == 'regular':
                        cfg = self.input_map.get(real_name, {})
                        if not cfg.get('persist', False):
                            self.flow_controller.flow_port_map[real_name].payload = None
                self.logger.debug(f"Emitted and releasing lock for trigger {self._pending_trigger}")
                self._is_processing = False
                self._pending_trigger = None
            return None
        return flow_fn

    def _update_template_storage(self, port_name, payload):
        """Update template storage for templates that depend on this port."""
        for template_name, deps in self.template_dependencies.items():
            if port_name in deps:
                if template_name not in self.template_storage:
                    self.template_storage[template_name] = {}
                self.template_storage[template_name][port_name] = payload

    # ---- Optional Items Handling ----
    
    def _is_optional(self, name):
        """Check if a name represents an optional item (enclosed in square brackets)."""
        return name.startswith('[') and name.endswith(']')
    
    def _get_real_name(self, name):
        """Get the real name from a potentially optional name."""
        if self._is_optional(name):
            return name[1:-1]  # Remove the square brackets
        return name

    # ---- Message Processing ----
    
    async def _process_messages(self, kwargs, messages_output, port_name):
        """Process messages using the appropriate strategy."""
        # Get message ordering based on strategy
        order = self._get_message_order(kwargs, port_name)
        
        # Skip processing if there's no ordering or if required dependencies are missing
        if not order or not self._has_required_dependencies(order):
            return False
            
        # If we get here, all required dependencies are satisfied
        messages = []
        
        # Get messages based on ordering - follow the order list exactly
        for name in order:
            msg = self._get_message(name)
            # Only add the message if it exists
            if msg:
                if isinstance(msg, list):
                    messages.extend(msg)
                else:
                    messages.append(msg)
            # If the message is required but missing, log a warning (could be an error in configuration)
            elif not self._is_optional(name):
                self.logger.warning(f"Warning: Required item '{name}' produced no message")
        
        # Emit messages if available
        if messages:
            await messages_output.emit(messages)
            return True
        return False

    def _get_message_order(self, kwargs, port_name):
        """
        Get the message ordering based on configured strategy.
        
        Priority:
        1. Custom build function (build_fn)
        2. Trigger map for the active port (trigger_map[port_name])
        3. Global emit order (emit_order)
        4. Fallback: all input items in sorted order
        """
        if self.build_fn:
            # When custom build function is provided, use it
            return self.build_fn(**kwargs)
        elif self.trigger_map and port_name in self.trigger_map:
            # When trigger_map is provided, use it
            return self.trigger_map[port_name]
        elif self.emit_order:
            # When only emit_order is provided, use it
            return self.emit_order
        else:
            # Fallback: use all items in the input_map
            return sorted(self.port_types.keys())

    def _has_required_dependencies(self, order):
        """
        Check if all required dependencies for a given message order are available.
        Uses pre-computed dependency sets for efficiency.
        
        Items marked with square brackets [like_this] are considered optional.
        All other items must have their full, non-optional dependency chains satisfied.
        """
        ports_needing_payloads = set()
        
        # Check each non-optional item in the order
        for item_spec in order:
            if self._is_optional(item_spec):
                continue
                
            real_name = self._get_real_name(item_spec)
            
            # 1. Check if the item itself is defined
            if real_name not in self.port_types:
                raise ValueError(f"Required item '{real_name}' listed in order is not defined in input_map.")
            
            # 2. Check the pre-computed dependency set for validity
            dep_set = self._full_dependency_sets.get(real_name)
            if dep_set is None:
                 # Should not happen if pre-computation ran correctly, but safety check
                #  self.logger.error(f"Dependency set for required item '{real_name}' was not pre-computed.")
                 return False 
            if dep_set == _INVALID_DEPENDENCY_MARKER:
                # self.logger.warning(f"Required item '{real_name}' has an undefined non-optional dependency.")
                return False
                
            # 3. Add valid dependencies to the set to check for payloads
            ports_needing_payloads.update(dep_set)

        # 4. Check if all identified regular ports have payloads
        for port_name in ports_needing_payloads:
            # This check assumes port_name was validated during pre-computation
            # We only store regular port names in the dependency sets
            port = self.flow_controller.flow_port_map.get(port_name)
            if not port or not port.payload:
                # self.logger.warning(f"Required dependency port '{port_name}' has no payload")
                return False
        
        return True

    def _check_dependency_payload(self, dep_name):
        """Helper to check if a dependency exists and has a payload if it's a regular port."""
        dep_type = self.port_types.get(dep_name)
        if dep_type is None:
            # Dependency itself is not defined
            self.logger.debug(f"Dependency '{dep_name}' not defined.")
            return False
        
        if dep_type == 'regular':
            port = self.flow_controller.flow_port_map.get(dep_name)
            if not port or not port.payload:
                # Regular port dependency exists but has no payload
                self.logger.debug(f"Dependency port '{dep_name}' has no payload.")
                return False
                
        # Dependency exists and is either not a regular port (e.g., constant) 
        # or it is a regular port with a payload.
        return True

    # ---- Message Retrieval and Conversion ----
    
    def _get_message(self, name):
        """
        Get a message for a given name based on its type. Assumes overall required 
        dependencies have already been validated by _has_required_dependencies.
        This method performs checks specific to the item itself (like 'depends_on').
        
        This handles all three types of items:
        - Constants: Return the pre-defined MessagePayload
        - Templates: Process the template with available dependencies
        - Regular ports: Convert the port payload to a MessagePayload
        """
        # Get real name and optional status
        real_name = self._get_real_name(name)
        is_optional = self._is_optional(name)
        
        # --- ADD BACK: Check item's specific 'depends_on' requirements ---
        # This check is necessary even if the item is optional in the order,
        # to determine if the item *can* be included based on its own rules.
        if real_name in self.dependencies:
            for dep_spec in self.dependencies[real_name]:
                 # An item cannot be included if *any* of its non-optional
                 # 'depends_on' requirements are not met.
                 if not self._is_optional(dep_spec):
                      real_dep_name = self._get_real_name(dep_spec)
                      if not self._check_dependency_payload(real_dep_name):
                           self.logger.debug(f"Item '{real_name}' skipped: non-optional dependency '{real_dep_name}' not met.")
                           return None # Cannot produce message if required dependencies are missing
        # --- END ADD BACK ---

        port_type = self.port_types.get(real_name)
        
        # Handle based on type
        if port_type == 'constant':
            # Constants are always available if defined
            return self.constants.get(real_name)
        
        elif port_type == 'template':
            template_data = self.templates.get(real_name)
            if template_data:
                # Attempt to process the template
                result = self._process_template(template_data, real_name)
                # If the template processing failed (e.g., missing *optional* dependency)
                # and the template itself was marked optional, return None.
                if result is None and is_optional:
                    return None
                # Otherwise, return the result (which could be None if a required dep was missing,
                # although _has_required_dependencies should prevent this).
                return result
            else:
                # Template definition not found (should not happen if defined in input_map)
                 self.logger.error(f"Template definition for '{real_name}' not found.")
                 return None
        
        elif port_type == 'regular':
            port = self.flow_controller.flow_port_map.get(real_name)
            # If the port or its payload is missing, return None.
            # _has_required_dependencies ensures payload exists if port is required.
            if port and port.payload is not None:
                role = self.port_roles.get(real_name)
                return self._convert_payload_to_message(real_name, port.payload, role)
            else:
                # If optional, None is fine. If required, this indicates an issue upstream.
                return None
        
        # If port_type is None (item not defined), return None
        self.logger.warning(f"Item '{real_name}' requested in order but not defined or processed.")
        return None

    def _process_template(self, template_data, template_name):
        """
        Process a template using its dependencies. Assumes required dependencies
        have been validated by _has_required_dependencies.
        
        Templates combine values from multiple ports into a single message.
        Dependencies can be marked as optional with square brackets.
        """
        role = template_data.get('role', 'system')
        template_str = template_data.get('template', '')
        
        # Get template variable dependencies
        deps = self.template_dependencies.get(template_name, [])
        
        # Build template context
        context = {}
        for dep_spec in deps:
            is_optional = self._is_optional(dep_spec)
            real_dep_name = self._get_real_name(dep_spec)
                
            port = self.flow_controller.flow_port_map.get(real_dep_name)
            
            # Get payload - port might be None if dependency wasn't in input_map
            payload = port.payload if port else None

            # --- Simplified Payload Check ---
            if payload is None:
                if is_optional:
                    # Skip this optional dependency, leave it out of context
                    continue 
                else:
                    # This is a required dependency but has no payload.
                    # This *should not happen* if _has_required_dependencies worked correctly.
                    self.logger.error(f"Required template dependency '{real_dep_name}' for '{template_name}' has no payload, despite passing initial checks.")
                    return None # Fail template processing

            # Convert payload to message content for the template context
            # We assume conversion works if payload is present
            msg = self._convert_payload_to_message(real_dep_name, payload, self.port_roles.get(real_dep_name))
            if msg is None:
                 # Conversion failed unexpectedly?
                 if is_optional:
                      continue
                 else:
                      self.logger.error(f"Failed to convert payload for required template dependency '{real_dep_name}' in template '{template_name}'.")
                      return None
                      
            context[real_dep_name] = msg.model.content if hasattr(msg, 'model') else str(msg)
            # --- End Simplified Check ---
        
        # Render template
        try:
            env = jinja2.Environment(undefined=jinja2.StrictUndefined)
            rendered = env.from_string(template_str).render(**context)
            return MessagePayload(content=rendered, role=role)
        except jinja2.exceptions.UndefinedError as e:
             # This usually happens if an optional dependency was skipped
             self.logger.debug(f"Template rendering skipped for '{template_name}' due to missing optional variable: {e}")
             return None # Fail template processing gracefully for missing optional vars
        except Exception as e:
            self.logger.error(f"Error rendering template '{template_name}': {str(e)}", exc_info=True)
            # Return an error message payload instead of None? Or stick with None?
            # Returning None indicates failure to build this part of the context.
            return None 

    def _convert_payload_to_message(self, name, payload, role=None):
        """
        Convert a payload to a MessagePayload with the specified role.
        
        Uses the payload_message_mapping to determine how to convert different payload types.
        """
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
            raise

    # ---- Dependency Pre-computation ----

    def _precompute_all_dependencies(self):
        """Calculate and store the full dependency set for every defined item."""
        # Ensure all items are computed, handling potential complex relationships
        all_items = list(self.port_types.keys())
        computed_count = 0
        while len(self._full_dependency_sets) < len(all_items) and computed_count < len(all_items) * 2:
             for item_name in all_items:
                 if item_name not in self._full_dependency_sets:
                     self._compute_full_dependencies(item_name, set())
             computed_count += 1 # Prevent infinite loops in weird edge cases
        if len(self._full_dependency_sets) != len(all_items):
             self.logger.error("Could not pre-compute dependencies for all items. Check for complex definition issues.")

    def _compute_full_dependencies(self, item_name, visited):
        """Recursively computes the full set of required regular ports for an item.
        
        Args:
            item_name (str): The name of the item to compute dependencies for.
            visited (set): A set of item names currently being visited to detect cycles.
            
        Returns:
            frozenset: A frozenset containing the names of all required regular ports,
                       or _INVALID_DEPENDENCY_MARKER if an undefined non-optional dependency is found.
        """
        real_name = self._get_real_name(item_name) 
        
        # Return cached result if already computed
        if real_name in self._full_dependency_sets:
            return self._full_dependency_sets[real_name]
        
        # Basic check: Does the item itself exist?
        item_type = self.port_types.get(real_name)
        if item_type is None:
             # This can happen if called for a dependency that isn't defined
             self.logger.debug(f"Dependency '{real_name}' is not defined in input_map.")
             return _INVALID_DEPENDENCY_MARKER

        # Detect cycles
        if real_name in visited:
            self.logger.warning(f"Dependency cycle detected involving '{real_name}'. Treating as invalid for this path.")
            return _INVALID_DEPENDENCY_MARKER # Cycles involving required dependencies make it impossible to satisfy
            
        visited.add(real_name)
        
        # Start with the item itself if it's a regular port
        required_ports = set()
        if item_type == 'regular':
            required_ports.add(real_name)
            
        is_valid = True # Flag to track if any sub-dependency is invalid

        # Add non-optional explicit dependencies (from 'depends_on')
        for dep_spec in self.dependencies.get(real_name, []):
            if not self._is_optional(dep_spec):
                dep_result = self._compute_full_dependencies(dep_spec, visited)
                if dep_result == _INVALID_DEPENDENCY_MARKER:
                    is_valid = False
                    break
                required_ports.update(dep_result)
        
        if not is_valid: 
             visited.remove(real_name)
             self._full_dependency_sets[real_name] = _INVALID_DEPENDENCY_MARKER
             return _INVALID_DEPENDENCY_MARKER
                    
        # Add non-optional template variable dependencies
        if item_type == 'template':
            for var_spec in self.template_dependencies.get(real_name, []):
                if not self._is_optional(var_spec):
                    var_result = self._compute_full_dependencies(var_spec, visited)
                    if var_result == _INVALID_DEPENDENCY_MARKER:
                         is_valid = False
                         break
                    required_ports.update(var_result)
        
        visited.remove(real_name) # Backtrack
        
        # Store the computed set (or invalid marker)
        final_result = frozenset(required_ports) if is_valid else _INVALID_DEPENDENCY_MARKER
        self._full_dependency_sets[real_name] = final_result
        return final_result