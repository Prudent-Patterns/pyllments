import param

from pyllments.elements.flow_control.flow_controller import FlowController
from pyllments.ports import OutputPort

class Router(param.Parameterized):
    key_port_map = param.Dict(allow_None=False)
    payload_key_fn = param.Callable(allow_None=False)

    flow_controller = param.ClassSelector(class_=FlowController)
    input_payload_type = param.Parameter(doc="""The payload type of the input port""")
    key_flow_port_map = param.Dict()
    incoming_output_port = param.ClassSelector(class_=OutputPort)

    def __init__(self, **params):
        super().__init__(**params)
        self._flow_controller_setup()
        if self.incoming_output_port:
            self.connect_input(self.incoming_output_port)

    def _flow_controller_setup(self):
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
     
    def _input_payload_type_set(self, key_port_map):
        payload_type = next(iter(key_port_map.values()))
        for port in key_port_map.values():
            if port.payload_type != payload_type:
                raise ValueError(f'All output ports must have the same payload type.')
        self.input_payload_type = payload_type

    def _flow_fn_setup(self, flow_map):
        def flow_fn(payload_input, multi_output, c, active_input_port):
            key = self.payload_key_fn(active_input_port.payload)
            self.key_flow_port_map[key].emit(active_input_port.payload)
        return flow_fn
    
    def connect_input(self, output_port):
        self.flow_controller.connect('payload_input', output_port)
