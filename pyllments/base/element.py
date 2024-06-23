import param

from pyllments.ports import InputPorts, OutputPorts

class Element(param.Parameterized):
    inputs = param.ClassSelector(class_=InputPorts, is_instance=True, default=InputPorts())
    outputs = param.ClassSelector(class_=OutputPorts, is_instance=True, default=OutputPorts())

    def __init__(self, **params):
        super().__init__(**params)
