from typing import Callable

import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.ports import Ports, OutputPort

class Router(param.Parameterized):
    """
    The Router class facilitates the routing of payloads between different flow ports in a flow control system.
    It acts as a mediator that connects input ports to multiple output ports based on a specified key.

    Parameters:
    -----------
    key_port_map : Dict[Any, OutputPort]
        A dictionary mapping keys to output ports. All output ports must have the same payload type.
    payload_key_fn : Callable
        A function that takes a payload as input and returns a key to determine which output port to use.
    incoming_output_port : OutputPort, optional
        An optional output port to connect to the router's input upon initialization.

    Attributes:
    -----------
    flow_controller : FlowController
        The underlying FlowController managing the routing logic.
    input_payload_type : Type
        The payload type of the input port, inferred from the key_port_map.
    key_flow_port_map : Dict[Any, OutputPort]
        A mapping of keys to the actual flow output ports created by the router.

    Usage:
    ------
    router = Router(
        key_port_map={
            'key1': output_port1,
            'key2': output_port2,
            # ...
        },
        payload_key_fn=lambda payload: payload.get_key(),
        incoming_output_port=some_output_port  # Optional
    )

    # To connect an input later:
    router.connect_input(some_other_output_port)

    Note:
    -----
    - All output ports in key_port_map must have the same payload type.
    - The payload_key_fn should return a key that exists in the key_port_map.
    """

    key_port_map = param.Dict(allow_None=False, doc="""
        A dictionary mapping keys to output ports. All output ports must have the same payload type.
        Example: {'key1': output_port1, 'key2': output_port2}""")
    
    payload_key_fn = param.Callable(allow_None=False, doc="""
        A function that takes a payload as input and returns a key to determine which output port to use.
        Example: lambda payload: payload.get_key()""")


    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        The underlying FlowController managing the routing logic.""")
    
    input_payload_type = param.Parameter(doc="The payload type of the input port, inferred from the key_port_map.")
    
    key_flow_port_map = param.Dict(doc="""
        A mapping of keys to the actual flow output ports created by the router.""")
    
    incoming_output_port = param.ClassSelector(class_=OutputPort, doc="""
        An optional output port to connect to the router's input upon initialization.""")
    
    ports = param.ClassSelector(class_=Ports, doc="""
        Handles the Port interface for the Element""")

    def __init__(self, **params):
        """
        Initialize the Router with the given parameters.

        Parameters:
        -----------
        **params : dict
            Keyword arguments that will be passed to param.Parameterized.__init__
        """
        super().__init__(**params)
        self._flow_controller_setup()
        self.ports = self.flow_controller.ports
        if self.incoming_output_port:
            self.connect_input(self.incoming_output_port)

    def _flow_controller_setup(self):
        """
        Set up the flow controller with the appropriate flow map and function.
        This method is called during initialization.
        """
        self._input_payload_type_set(self.key_port_map)
        flow_map = {
            'input': {
                'payload_input': self.input_payload_type,
            },
            'output': {
                'multi_output': self.input_payload_type,
            }
        }

        flow_fn = self._flow_fn_setup(flow_map)
        self.flow_controller = FlowController(flow_fn=flow_fn, flow_map=flow_map)
        
        for key, port in self.key_port_map.items():
            flow_output_port = self.flow_controller.connect('multi_output', port)
            self.key_flow_port_map[key] = flow_output_port
     
    def _input_payload_type_set(self, key_port_map: dict[str, OutputPort]):
        """
        Set the input payload type based on the key_port_map.

        Parameters:
        -----------
        key_port_map : Dict[str, OutputPort]
            The dictionary mapping keys to output ports.

        Raises:
        -------
        ValueError
            If all output ports in the key_port_map don't have the same payload type.
        """
        payload_type = next(iter(key_port_map.values()))
        for port in key_port_map.values():
            if port.payload_type != payload_type:
                raise ValueError(f'All output ports must have the same payload type.')
        self.input_payload_type = payload_type

    def _flow_fn_setup(self, flow_map: dict) -> Callable:
        """
        Set up the flow function for the FlowController.

        Parameters:
        -----------
        flow_map : dict
            The flow map dictionary defining input and output ports.

        Returns:
        --------
        Callable
            The flow function to be used by the FlowController.
        """
        def flow_fn(payload_input, multi_output, c, active_input_port):
            key = self.payload_key_fn(active_input_port.payload)
            self.key_flow_port_map[key].emit(active_input_port.payload)
        return flow_fn
    
    def connect_input(self, output_port: OutputPort):
        """
        Connect an output port to the router's input.

        Parameters:
        -----------
        output_port : OutputPort
            The output port to connect to the router's input.
        """
        self.flow_controller.connect('payload_input', output_port)
