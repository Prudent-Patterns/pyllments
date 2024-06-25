import param

from pyllments.base import Payload

class OutputPort(param.Parameterized):
    output_map = param.Dict(default=dict())
    payload_type = param.ClassSelector(class_=Payload)

    def add_output(self, parameter, ):
        new_param = param.Parameter(default=None, allow_refs=True, per_instance=True)
        self.param.add_parameter(parameter.name, new_param)
        self.param.update({parameter.name: parameter})
        self.output_map[parameter.name] = []
    
    def emit(self, ):
        pass
    def stage(self, ):
        pass

class InputPort(param.Parameterized):
    inputs = param.List(item_type=tuple[str, str]) 

    def add_input(self, parameter, element=None):
        new_param = param.Parameter(default=None, allow_refs=True, per_instance=True) #TODO first str should be the Element superclass
        self.param.add_parameter(parameter.name, new_param)
        self.param.update({parameter.name: parameter})
        self.inputs.append((element, parameter.name))
