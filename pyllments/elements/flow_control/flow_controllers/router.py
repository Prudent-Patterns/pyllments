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
        A dict mapping the output port name to a predicate function that returns True if
        the payload should be routed to that output port. Predicates are evaluated in the
        order they are defined in the dictionary.
        Example: {'some_output': lambda payload: payload.model.content == "Yes"}""")
    
    connected_output_map = param.Dict(default={}, doc="""
        A dict mapping the output port name to a dictionary of ports to connect and a
        predicate function that returns True if the payload should be routed to that output port.
        Example: {
            'output_port_a': {
                'ports': [el1.ports.some_input],
                'predicate': lambda payload: payload.model.content == "Yes"
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
        if not (self.output_map or self.connected_output_map):
            raise ValueError("At least one of output_map or connected_output_map must be provided.")
        
        # Setup flow map with input port and output ports using the explicit payload_type
        flow_map = {
            'input': {
                'payload_input': self.payload_type,
            },
            'output': {}
        }
        
        # Add output ports to the flow map
        for port_name in self.output_map:
            flow_map['output'][port_name] = self.payload_type
        
        # Setup connected flow map
        connected_flow_map = {'input': {}, 'output': {}}
        
        # Add incoming_output_port to the connected_flow_map if provided
        if self.incoming_output_port is not None:
            connected_flow_map['input']['payload_input'] = [self.incoming_output_port]
            
        # Add output connections from connected_output_map
        if self.connected_output_map:
            for port_name, config in self.connected_output_map.items():
                ports = config.get('ports', [])
                if ports:
                    connected_flow_map['output'][port_name] = ports if isinstance(ports, list) else [ports]
        
        # Create the flow function
        flow_fn = self._flow_fn_setup()
        
        # Create the flow controller
        flow_controller_kwargs = {
            'flow_fn': flow_fn,
            'flow_map': flow_map,
            'connected_flow_map': connected_flow_map,
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
            
            # First check predicates from output_map
            for port_name, predicate in self.output_map.items():
                if predicate(payload):
                    if port_name in kwargs:
                        output_port = kwargs[port_name]
                        output_port.emit(payload)
                        return
            
            # Then check predicates from connected_output_map
            for port_name, config in self.connected_output_map.items():
                predicate = config.get('predicate')
                if predicate and predicate(payload):
                    if port_name in kwargs:
                        output_port = kwargs[port_name]
                        output_port.emit(payload)
                        return
        
        return flow_fn