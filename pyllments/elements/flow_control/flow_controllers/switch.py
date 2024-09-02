import param

from pyllments.base.payload_base import Payload
from pyllments.elements.flow_control import FlowController
from pyllments.ports import OutputPort, InputPort, Ports


class Switch(param.Parameterized):
    """
    The Switch class routes an input payload to one of multiple output ports based on the current_output setting.

    Parameters:
    -----------
    payload_type : Type[Payload]
        The type of payload that this switch will handle.
    outputs : List[str], optional
        A list of output port aliases.
    connected_map : Dict[str, Dict[str, Union[InputPort, OutputPort, List[InputPort], List[OutputPort]]]], optional
        A dictionary mapping input and output aliases to ports for connection.
    current_output : str
        The currently active output port alias.

    Attributes:
    -----------
    flow_controller : FlowController
        The underlying FlowController managing the routing logic.
    ports : Ports
        The ports object containing all input and output ports.

    Usage:
    ------
    # Create a Switch with a list of output aliases, then connect it.
    switch = Switch(
        outputs=['output1', 'output2'],
        payload_type=MessagePayload,
        current_output='output1'
    )
    input_element.ports.output['test_output'] > switch.ports.input['payload_input']
    switch.ports.output['output1'] > output_element1.ports.input['test_input']
    switch.ports.output['output2'] > output_element2.ports.input['test_input']


    # Create a Switch with a connected map specifying input and output ports
    switch = Switch(
        payload_type=MessagePayload,
        connected_map={
            'input': {
                'payload_input': [el1.ports.output['output1'], el2.ports.output['output2']],
            },
            'output': {
                'port1': [el3.ports.input['input1'], el4.ports.input['input2']],
                'port2': el5.ports.input['input3']
            }
        },
        current_output='port1'
    )

    # To change the active output port:
    switch.current_output = 'port2'
    """

    payload_type = param.ClassSelector(class_=Payload, is_instance=False, doc="Type of payload this switch will handle")
    outputs = param.List(default=[], item_type=str, doc="List of output port aliases")
    connected_map = param.Dict(default={}, doc="""
        Dictionary of input and output aliases mapped to ports for connection.
        Example:
        {
            'input': {
                'payload_input': [el1.ports.output['output1'], el2.ports.output['output2']],
            },
            'output': {
                'port1': [el3.ports.input['input1'], el4.ports.input['input2']],
                'port2': el5.ports.input['input3']
            }
        }
        """)
    
    current_output = param.String(doc="Currently active output port")

    flow_controller = param.ClassSelector(class_=FlowController, doc="FlowController object")
    ports = param.ClassSelector(class_=Ports, allow_None=False, doc="Ports object")

    def __init__(self, **params):
        super().__init__(**params)
        self._flow_controller_setup()

    def _flow_map_setup(self):
        flow_map = {'input': {'payload_input': self.payload_type}, 'output': {}}
        for output in self.outputs:
            flow_map['output'][output] = self.payload_type
        return flow_map

    def _connected_flow_map_setup(self):
        connected_flow_map = {'input': {}, 'output': {}}
        
        # Handle input connections
        if 'input' in self.connected_map:
            for key, ports in self.connected_map['input'].items():
                if isinstance(ports, (list, tuple)):
                    connected_flow_map['input'][key] = ports
                elif isinstance(ports, OutputPort):
                    connected_flow_map['input'][key] = [ports]
                else:
                    raise ValueError(f"Invalid value for input key '{key}': {ports}")
        
        # Handle output connections
        if 'output' in self.connected_map:
            for key, ports in self.connected_map['output'].items():
                if isinstance(ports, (list, tuple)):
                    connected_flow_map['output'][key] = ports
                elif isinstance(ports, InputPort):
                    connected_flow_map['output'][key] = [ports]
                else:
                    raise ValueError(f"Invalid value for output key '{key}': {ports}")
        
        # Merge outputs from both outputs list and connected_map
        merged_outputs = set(self.outputs)
        merged_outputs.update(connected_flow_map['output'].keys())
        self.outputs = list(merged_outputs)
        
        return connected_flow_map

    def _flow_controller_setup(self):
        flow_map = self._flow_map_setup()
        connected_flow_map = self._connected_flow_map_setup()
        
        def flow_fn(payload_input, c, active_input_port, **kwargs):
            if self.current_output in kwargs:
                kwargs[self.current_output].emit(active_input_port.payload)

        self.flow_controller = FlowController(flow_fn=flow_fn, flow_map=flow_map, connected_flow_map=connected_flow_map)
        self.ports = self.flow_controller.ports
        
        # Set up the current_output parameter
        if not self.current_output and self.outputs:
            self.current_output = self.outputs[0]
