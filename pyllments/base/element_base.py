import warnings

import param

from .model_base import Model
from ..ports import Ports
from ..common.style_helpers import get_method_name

class Element(param.Parameterized):

    """Base class for all elements in the framework"""
    model = param.ClassSelector(class_=Model)
    ports = param.ClassSelector(class_=Ports)

    def __init__(self, **params):
        super().__init__(**params)
        self.ports = Ports(containing_element=self)
    
    @classmethod
    def get_base_path(cls):
        # Get the module where the class is defined
        module = sys.modules[cls.__module__]
        # Return the parent directory of the module's file
        return Path(module.__file__)
    
    def load_css(self):
        css = get_method_name(prefix='create_', suffix='_view', level=2)
        if css not in type(self)._css_cache:

            with 
            self._css_cache[css] = self._load_css(css_filename)
        return self._css_cache[css_filename]

    def _view_exists(self, view):
        if view:
            warnings.warn(f'{view} already exists. Returning existing view.')
            return True
    
    @staticmethod
    def port_emit_if_exists(port_name: str):
        """
        Used to decorate a watch method so that when it runs, it emits
        the port labelled with the port_name if the port is established. 
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if port_name in self.ports.input:
                    self.ports.input[port_name].emit()
                elif port_name in self.ports.output:
                    self.ports.output[port_name].emit()
                return
            return wrapper
        return decorator

    @staticmethod
    def port_stage_if_exists(port_name: str, model_param_name: str):
        """
        Used to decorate a watch method so that when it runs, it stages a
        model parameter on a port if both are established
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if (model_param := getattr(self.model, model_param_name)):
                    if port_name in self.ports.input:
                        self.ports.input[port_name].stage(**{model_param_name: model_param})
                    elif port_name in self.ports.output:
                        self.ports.output[port_name].stage(**{model_param_name: model_param})
                return
            return wrapper
        return decorator
    
    @staticmethod
    def port_stage_emit_if_exists(port_name: str, model_param_name: str):
        """
        Used to decorate a watch method and emit the port labelled with the
        port_name if the port is established. 
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if (model_param := getattr(self.model, model_param_name)):
                    if port_name in self.ports.input:
                        self.ports.input[port_name].stage(**{model_param_name: model_param})
                    elif port_name in self.ports.output:
                        self.ports.output[port_name].stage_emit(**{model_param_name: model_param})
                return
            return wrapper
        return decorator
