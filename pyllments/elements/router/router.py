from typing import Callable

import param

from pyllments.elements.flow_control import FlowController
from pyllments.ports import Ports, OutputPort
from pyllments.base.element_base import Element

class Router(Element):
    """
    The Router class facilitates the routing of payloads between different flow ports in a flow control system.
    It routes incoming payloads to different output ports based on predicate functions.
    """

    payload_type = param.Parameter(doc="""
        The payload type for all ports in the router. All ports will use the same payload type.""")

    output_map = param.Dict(default={}, doc="""
        A dict mapping the output port name to a config dict with 'predicate' (required) and optional 'ports' list.
        Predicates are evaluated in the order they are defined in the dictionary.
        Example: {
            'some_output': {
                'predicate': lambda payload: payload.model.content == "Yes",
                'ports': [el1.ports.input['some_input']]
            }
        }""")
    
    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")
    
    incoming_output_port = param.ClassSelector(class_=OutputPort, default=None, doc="""
        An optional output port to connect to the router's input upon initialization.""")
    
    ports = param.ClassSelector(class_=Ports, doc="""
        Handles the Port interface for the Element""")

    def __init__(self, **params):
        super().__init__(**params)
        self._flow_controller_setup()
        self.ports = self.flow_controller.ports

    def _flow_controller_setup(self):
        """
        Set up the flow controller with the appropriate flow map and function.
        This method is called during initialization.
        """
        if not self.output_map:
            raise ValueError("output_map must be provided.")
        
        # Setup flow map with input port and output ports using the explicit payload_type
        flow_map = {
            'input': {
                'payload_input': {
                    'payload_type': self.payload_type,
                }
            },
            'output': {}
        }
        
        # Add incoming_output_port to the flow_map if provided
        if self.incoming_output_port is not None:
            flow_map['input']['payload_input']['ports'] = [self.incoming_output_port]
            
        # Add output ports to the flow map
        for port_name, config in self.output_map.items():
            if 'predicate' not in config:
                raise ValueError(f"Predicate missing for output port '{port_name}'")
            output_config = {'payload_type': self.payload_type}
            ports = config.get('ports')
            if ports:
                output_config['ports'] = ports if isinstance(ports, list) else [ports]
            flow_map['output'][port_name] = output_config
        
        # Create the flow function
        flow_fn = self._flow_fn_setup()
        
        # Create the flow controller
        flow_controller_kwargs = {
            'flow_fn': flow_fn,
            'flow_map': flow_map,
            'containing_element': self
        }
            
        self.flow_controller = FlowController(**flow_controller_kwargs)
     
    def _flow_fn_setup(self) -> Callable:
        """
        Set up the flow function for the FlowController.
        
        Returns:
        --------
        Callable
            The flow function to be used by the FlowController.
        """
        def flow_fn(payload_input, c, active_input_port, **kwargs):
            payload = active_input_port.payload
            
            for port_name, config in self.output_map.items():
                predicate = config['predicate']
                if predicate(payload):
                    if port_name in kwargs:
                        output_port = kwargs[port_name]
                        output_port.emit(payload)
                        return
        
        return flow_fn