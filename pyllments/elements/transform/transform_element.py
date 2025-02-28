import param
from loguru import logger

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.elements.flow_control import FlowController
from pyllments.ports import InputPort



class TransformElement(Element):
    input_map = param.Dict(default={}, doc="""
        A dictionary mapping port names to their configuration.
        
        Each entry should have a 'payload_type' key specifying the expected payload type.
        An optional 'persist' flag (defaults to False) can be set to True to keep the payload
        in memory after transformation.
        
        Example:
        input_map = {
            'port_a': {'payload_type': MessagePayload},
            'port_b': {'payload_type': MessagePayload, 'persist': True}
        }"""
    )
        
    
    connected_input_map = param.Dict(default={}, doc="""
        A dictionary mapping port names to their connection configuration.
        
        Each entry should have a 'ports' key containing a list of output ports to connect to.
        An optional 'payload_type' key can specify the expected payload type.
        An optional 'persist' flag (defaults to False) can be set to True to keep the payload
        in memory after transformation.
        
        Example:
        connected_input_map = {
            'port_a': {
                'payload_type': MessagePayload,
                'ports': [el1.ports.output['some_output']]
            },
            'port_b': {
                'payload_type': MessagePayload,
                'persist': True,
                'ports': [el2.ports.output['some_output']]
            }
        }"""
    )

    output_payload_type = param.ClassSelector(default=None, is_instance=False, class_=Payload, doc="""
        The payload type for the output port.
        
        This can be explicitly provided or automatically inferred from the return type
        annotation of the emit_fn. At least one of these must be specified.""")
        
    emit_fn = param.Callable(default=None, doc="""
        A function that transforms input payloads into an output payload.
        
        This function is called when all required input payloads are available.
        The function parameters should match the port names in input_map or connected_input_map,
        and each parameter will receive the corresponding port's payload.
        
        Example:
        def emit_fn(port_a, port_b) -> MessagePayload:
            return MessagePayload(content=port_a.model.content + port_b.model.content)
        """
    )

    trigger_map = param.Dict(default={}, doc="""
        A dictionary mapping port names to transformation configurations.
        
        When a payload arrives at a port listed as a key in this map, the specified
        function will be called if all required ports (listed in 'ports') have payloads.
        
        Each entry should have:
        - 'function': The transformation function to call
        - 'ports': A list of port names whose payloads will be passed to the function
        
        Example:
        def fn1(port_a, port_b):
            return MessagePayload(content=port_a.model.content + port_b.model.content)
            
        trigger_map = {
            'port_a': {'function': fn1, 'ports': ['port_a', 'port_b']},
            'port_b': {'function': fn1, 'ports': ['port_b']}
        }"""
    )

    build_fn = param.Callable(default=None, doc="""
        A function providing full control over the transformation process.
        
        This function is called whenever any input port receives a payload.
        It receives all available port payloads as named arguments, plus:
        - active_input_port: The port that just received a payload
        - c: A persistent context dictionary for storing state between calls
        
        The function should return a payload to be emitted, or None if no emission is needed.
        Unlike emit_fn and trigger_map, build_fn has full control over payload persistence
        and can manage the context dictionary directly.
        
        Example:
        def build_fn(port_a, port_b, active_input_port, c):
            # Store conversation state in context
            if 'history' not in c:
                c['history'] = []
                
            if active_input_port.name == 'port_a':
                c['history'].append(port_a.model.content)
                return MessagePayload(content=f"Received: {port_a.model.content}")
            elif port_b is not None:
                combined = " + ".join(c['history']) + " + " + port_b.model.content
                return MessagePayload(content=combined)
            return None
        """
    )
    
    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.
        
        This is automatically created during initialization and manages the flow
        of payloads between ports.""")
    
    outgoing_input_port = param.ClassSelector(class_=InputPort, doc="""
        An optional input port to connect to the transform_output port upon initialization.
        
        This allows for easy chaining of elements by automatically connecting this element's
        output to another element's input.""")
    
    def __init__(self, **params):
        super().__init__(**params)
        
        # Check required parameters
        if not (self.input_map or self.connected_input_map):
            raise ValueError("At least one of input_map or connected_input_map must be provided.")
        
        # Determine output payload type
        self._determine_output_payload_type()
        
        # Validate that at least one transformation strategy is provided
        if not any([self.emit_fn, self.trigger_map, self.build_fn]):
            raise ValueError("At least one of emit_fn, trigger_map, or build_fn must be provided")
        
        # Initialize lookup tables and build flow maps
        self.port_persist = []  # List of port names that should persist
        flow_map, connected_flow_map = self._build_flow_maps()
        
        # Create the flow controller with the transform flow function
        transform_flow_fn = self._create_transform_flow_fn()
        
        self.flow_controller = FlowController(
            containing_element=self,
            flow_map=flow_map,
            connected_flow_map=connected_flow_map,
            flow_fn=transform_flow_fn
        )
        
        # Store the ports for easy access
        self.ports = self.flow_controller.ports
        
        # Connect outgoing port if provided
        if self.outgoing_input_port:
            self.ports.output['transform_output'] > self.outgoing_input_port
    
    def _build_flow_maps(self):
        """Build flow_map and connected_flow_map for the FlowController.
        
        This method processes both input_map and connected_input_map to:
        1. Create properly structured flow maps for the FlowController
        2. Register persistence flags for ports
        3. Ensure consistent payload type information
        
        Returns:
            tuple: (flow_map, connected_flow_map)
        """
        # Initialize flow maps with empty structures
        flow_map = {
            'input': {},
            'output': {'transform_output': self.output_payload_type}
        }
        
        connected_flow_map = {
            'input': {},
            'output': {}
        }
        
        # Process input_map
        self._process_input_map(flow_map)
        
        # Process connected_input_map
        self._process_connected_input_map(flow_map, connected_flow_map)
        
        return flow_map, connected_flow_map
    
    def _process_input_map(self, flow_map):
        """Process input_map to build flow_map and register persistence flags.
        
        Args:
            flow_map (dict): The flow map to populate
        """
        for key, config in self.input_map.items():
            # Add to flow_map input section
            if isinstance(config, dict) and 'payload_type' in config:
                flow_map['input'][key] = config['payload_type']
                
                # Register persistence flag
                if config.get('persist', False) and key not in self.port_persist:
                    self.port_persist.append(key)
            elif not isinstance(config, dict):
                # If config is a type directly
                flow_map['input'][key] = config
    
    def _process_connected_input_map(self, flow_map, connected_flow_map):
        """Process connected_input_map to build both flow maps and register persistence flags.
        
        Args:
            flow_map (dict): The flow map to populate
            connected_flow_map (dict): The connected flow map to populate
        """
        for key, config in self.connected_input_map.items():
            if isinstance(config, dict):
                # Add ports to connected_flow_map if available
                if 'ports' in config:
                    ports = config['ports']
                    connected_flow_map['input'][key] = ports
                
                # Add payload_type to flow_map if specified and not already added
                if 'payload_type' in config and key not in flow_map['input']:
                    flow_map['input'][key] = config['payload_type']
                
                # Register persistence flag
                if config.get('persist', False) and key not in self.port_persist:
                    self.port_persist.append(key)
    
    def _determine_output_payload_type(self):
        """Determine the output payload type from emit_fn return annotation if not explicitly provided."""
        if self.output_payload_type is None and self.emit_fn is not None:
            from inspect import signature
            sig = signature(self.emit_fn)
            if sig.return_annotation is not sig.empty:
                self.output_payload_type = sig.return_annotation
        
        if self.output_payload_type is None:
            raise ValueError("output_payload_type must be provided or inferable from emit_fn return annotation")
    
    def _create_transform_flow_fn(self):
        """Create the flow function for the FlowController."""
        def transform_flow_fn(**kwargs):
            """Flow function that handles the transformation logic."""
            # Extract key arguments
            active_input_port = kwargs.get('active_input_port')
            transform_output = kwargs.get('transform_output')
            
            if not active_input_port or not transform_output:
                return None
                
            c = kwargs.get('c', {})  # Context dict provided by FlowController
            port_name = active_input_port.name
            
            # Initialize payload tracking dict if not present
            if 'input_name_payload_dict' not in c:
                c['input_name_payload_dict'] = {}
            
            # Store the incoming payload
            if active_input_port.payload is not None:
                c['input_name_payload_dict'][port_name] = active_input_port.payload
            
            # Track inputs used in successful transformations
            if 'inputs_used_in_transformation' not in c:
                c['inputs_used_in_transformation'] = set()
            
            # Flag to track if processing was done
            processing_successful = False
            result = None
            
            # Strategy 1: Use build_fn if available (highest priority)
            if self.build_fn:
                # Prepare kwargs for build_fn
                build_fn_kwargs = {
                    'active_input_port': active_input_port,
                    'c': c
                }
                
                # Add all available payloads as kwargs
                for port, payload in c['input_name_payload_dict'].items():
                    build_fn_kwargs[port] = payload
                
                try:
                    # Call the build function
                    result = self.build_fn(**build_fn_kwargs)
                    
                    if result is not None:
                        # Emit result to the transform_output port
                        transform_output.emit(result)
                        processing_successful = True
                except Exception as e:
                    logger.error(f"Error in build_fn: {e}")
            
            # Strategy 2: Use trigger_map if applicable
            elif self.trigger_map and port_name in self.trigger_map:
                trigger_config = self.trigger_map[port_name]
                required_ports = trigger_config.get('ports', [])
                transform_fn = trigger_config.get('function')
                
                # Check if we have all required payloads
                have_all_required = all(port in c['input_name_payload_dict'] for port in required_ports)
                
                if have_all_required:
                    # Prepare function kwargs with payloads
                    fn_kwargs = {}
                    for port in required_ports:
                        fn_kwargs[port] = c['input_name_payload_dict'][port]
                    
                    try:
                        # Call the transformation function
                        result = transform_fn(**fn_kwargs)
                        
                        if result is not None:
                            # Emit result to the transform_output port
                            transform_output.emit(result)
                            processing_successful = True
                            
                            # Record which inputs were used in this transformation
                            c['inputs_used_in_transformation'].update(required_ports)
                    except Exception as e:
                        logger.error(f"Error in trigger_map function: {e}")
            
            # Strategy 3: Use emit_fn if all required inputs are available
            elif self.emit_fn:
                # Get all required parameters from the emit_fn signature
                from inspect import signature
                sig = signature(self.emit_fn)
                required_params = list(sig.parameters.keys())
                
                # Check if we have all required payloads
                have_all_required = all(param in c['input_name_payload_dict'] for param in required_params)
                
                if have_all_required:
                    # Prepare function kwargs with payloads
                    fn_kwargs = {}
                    for param in required_params:
                        fn_kwargs[param] = c['input_name_payload_dict'][param]
                    
                    try:
                        # Call the emit function
                        result = self.emit_fn(**fn_kwargs)
                        
                        if result is not None:
                            # Emit result to the transform_output port
                            transform_output.emit(result)
                            processing_successful = True
                            
                            # Record which inputs were used in this transformation
                            c['inputs_used_in_transformation'].update(required_params)
                    except Exception as e:
                        logger.error(f"Error in emit_fn: {e}")
            
            # Clean up non-persisted payloads, but ONLY if they were used in a transformation
            if processing_successful:
                # Get list of ports used in this or previous transformations
                used_ports = c.get('inputs_used_in_transformation', set())
                
                for p_name in list(c['input_name_payload_dict'].keys()):
                    # Only remove payloads that:
                    # 1. Have been used in a transformation
                    # 2. Are not explicitly marked to persist
                    if p_name in used_ports and p_name not in self.port_persist:
                        c['input_name_payload_dict'].pop(p_name, None)
                        # Remove from used set to prevent double processing
                        c['inputs_used_in_transformation'].discard(p_name)
            
            return result
        
        return transform_flow_fn