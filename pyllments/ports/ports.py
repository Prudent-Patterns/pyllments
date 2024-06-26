import param

from pyllments.base import Payload

class Port(param.Parameterized):
    payload = param.ClassSelector(class_=Payload)
    containing_element = param.Parameter(default=None)
    connected_elements = param.List()

class InputPort(Port):
    subject_ports = param.List(item_type=Port)
    unpack_payload_callback = param.Callable(default=None)

    def receive(self, payload):
        pass

    def unpack_payload(self, payload):
        pass

class OutputPort(Port):
    observer_ports = param.List(item_type=Port)
    pack_payload_callback = param.Callable(default=None)
    emit_when_ready = param.Boolean(default=True)
    staged_objects = param.List()
    required_objects = param.List()
    
    def emit(self):
        for port in self.observer_ports:
            port.receive(payload)
    
    def stage(self, objs):
        

    def pack_payload(self):
        if self.pack_payload_callback:
            return self.pack_payload_callback()
        else:
            return self.payload_type()
    
    def stage_and_emit(self, ):
        self.stage()
        self.emit()

    def connect(self, other):
        """Connects self and the InputPort"""
        if type(other) is not InputPort:
            raise ValueError('Can only connect OutputPorts to InputPorts')
        if type(other.payload) != type(self.payload):
            raise ValueError('InputPort and OutputPort payload types must match')
        self.observer_ports.append(other)
        other.connected_elements.append(self.containing_element)

    def __gt__(self, other):
        """Implements self.connect(other)"""

        self.connect(self, other)
        

class Ports(param.Parameterized):
    """Keeps track of InputPorts and OutputPorts and handles their creation"""
    input = param.List(item_type=InputPort)
    output = param.List(item_type=OutputPort)
    containing_element = param.Parameter(default=None)

    def add_input(self, name, payload_type, ):
        input_port = InputPort(
            name=name,
            payload=payload_type(),
            containing_element=self.containing_element
            )
        self.param.add_parameter(name, param.Parameter(input_port))
        self.input.append(input_port)
        return input_port
    
    def add_output(self, name, payload_type, ):
        output_port = OutputPort(
            name=name,
            payload=payload_type(),
            containing_element=self.containing_element
            )
        self.output.append(output_port)
        return output_port
