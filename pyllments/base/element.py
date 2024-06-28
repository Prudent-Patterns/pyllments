import param

from pyllments.ports import InputPorts, OutputPorts

class Element(param.Parameterized):
    model = param.ClassSelector(class_=Model, default=None)
    ports = param.ClassSelector(class_=Ports)

    def __init__(self, **params):
        super().__init__(**params)
        self.ports = Ports(containing_element=self)
