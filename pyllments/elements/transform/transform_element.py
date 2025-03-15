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
        
        Optionally, a 'ports' key can contain a list of output ports to connect to this input.
        
        Example:
        input_map = {
            'port_a_input': {'payload_type': MessagePayload},
            'port_b_input': {
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
        The function parameters should match the port names in input_map,
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
        
        # Ensure that input_map is provided
        if not self.input_map:
            raise ValueError("input_map must be provided.")
        
        # Determine output payload type (from emit_fn return type if necessary)
        self._determine_output_payload_type()
        
        # Validate that at least one transformation strategy is provided
        if not any([self.emit_fn, self.trigger_map, self.build_fn]):
            raise ValueError("At least one of emit_fn, trigger_map, or build_fn must be provided")
        
        # Initialize persistence list and build unified flow map from input_map.
        self.port_persist = []  # List of port names that should persist
        flow_map = self._build_flow_map()
        
        # Create the flow controller with the transform flow function.
        transform_flow_fn = self._create_transform_flow_fn()
        
        self.flow_controller = FlowController(
            containing_element=self,
            flow_map=flow_map,
            flow_fn=transform_flow_fn
        )
        
        # Store the ports for easy access.
        self.ports = self.flow_controller.ports
        
        # Automatically connect outgoing port if provided.
        if self.outgoing_input_port:
            self.ports.output['transform_output'] > self.outgoing_input_port
    
    def _build_flow_map(self):
        """
        Build a flow map for the FlowController by processing the input_map.
        Consolidates all configurations into a single mapping.
        
        Returns:
            dict: A dictionary with 'input' and 'output' configurations.
        """
        flow_map = {
            'input': {},
            'output': {'transform_output': {"payload_type": self.output_payload_type}}
        }
        
        for key, config in self.input_map.items():
            if isinstance(config, dict):
                # Use the entire configuration dict directly.
                flow_map['input'][key] = config
                # Register persistence flag if required.
                if config.get('persist', False) and key not in self.port_persist:
                    self.port_persist.append(key)
            else:
                # If the configuration is supplied as a type directly, wrap it in a dict.
                flow_map['input'][key] = {"payload_type": config}
        
        return flow_map
    
    def _determine_output_payload_type(self):
        """
        Determine the output payload type from the emit_fn's return annotation if not explicitly provided.
        """
        if self.output_payload_type is None and self.emit_fn is not None:
            from inspect import signature
            sig = signature(self.emit_fn)
            if sig.return_annotation is not sig.empty:
                self.output_payload_type = sig.return_annotation
        
        if self.output_payload_type is None:
            raise ValueError("output_payload_type must be provided or inferable from emit_fn return annotation")
    
    def _create_transform_flow_fn(self):
        """
        Create the flow function for the FlowController.
        This function handles payload transformation using build_fn, trigger_map, or emit_fn strategies.
        
        Returns:
            function: The flow function to be passed to the FlowController.
        """
        def transform_flow_fn(**kwargs):
            # Extract key arguments for processing.
            active_input_port = kwargs.get('active_input_port')
            transform_output = kwargs.get('transform_output')
            
            if not active_input_port or not transform_output:
                return None
                
            c = kwargs.get('c', {})  # Context dict provided by FlowController.
            port_name = active_input_port.name
            
            # Initialize payload tracking dict if not present.
            if 'input_name_payload_dict' not in c:
                c['input_name_payload_dict'] = {}
            
            # Store the incoming payload.
            if active_input_port.payload is not None:
                c['input_name_payload_dict'][port_name] = active_input_port.payload
            
            # Track inputs used in successful transformations.
            if 'inputs_used_in_transformation' not in c:
                c['inputs_used_in_transformation'] = set()
            
            # Flag to indicate if processing was successful.
            processing_successful = False
            result = None
            
            # Strategy 1: Use build_fn if available (highest priority).
            if self.build_fn:
                build_fn_kwargs = {
                    'active_input_port': active_input_port,
                    'c': c
                }
                # Include all available payloads.
                for port, payload in c['input_name_payload_dict'].items():
                    build_fn_kwargs[port] = payload
                
                try:
                    result = self.build_fn(**build_fn_kwargs)
                    if result is not None:
                        transform_output.emit(result)
                        processing_successful = True
                except Exception as e:
                    logger.error(f"Error in build_fn: {e}")
            
            # Strategy 2: Use trigger_map if defined for this port.
            elif self.trigger_map and port_name in self.trigger_map:
                trigger_config = self.trigger_map[port_name]
                required_ports = trigger_config.get('ports', [])
                transform_fn = trigger_config.get('function')
                
                have_all_required = all(p in c['input_name_payload_dict'] for p in required_ports)
                if have_all_required:
                    fn_kwargs = {p: c['input_name_payload_dict'][p] for p in required_ports}
                    try:
                        result = transform_fn(**fn_kwargs)
                        if result is not None:
                            transform_output.emit(result)
                            processing_successful = True
                            c['inputs_used_in_transformation'].update(required_ports)
                    except Exception as e:
                        logger.error(f"Error in trigger_map function: {e}")
            
            # Strategy 3: Use emit_fn if all required inputs are available.
            elif self.emit_fn:
                from inspect import signature
                sig = signature(self.emit_fn)
                required_params = list(sig.parameters.keys())
                
                have_all_required = all(param in c['input_name_payload_dict'] for param in required_params)
                if have_all_required:
                    fn_kwargs = {param: c['input_name_payload_dict'][param] for param in required_params}
                    try:
                        result = self.emit_fn(**fn_kwargs)
                        if result is not None:
                            transform_output.emit(result)
                            processing_successful = True
                            c['inputs_used_in_transformation'].update(required_params)
                    except Exception as e:
                        logger.error(f"Error in emit_fn: {e}")
            
            # Clean up non-persisted payloads once processing is successful.
            if processing_successful:
                used_ports = c.get('inputs_used_in_transformation', set())
                for p_name in list(c['input_name_payload_dict'].keys()):
                    if p_name in used_ports and p_name not in self.port_persist:
                        c['input_name_payload_dict'].pop(p_name, None)
                        c['inputs_used_in_transformation'].discard(p_name)
            
            return result
        
        return transform_flow_fn