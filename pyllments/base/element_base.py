import warnings
import sys
from pathlib import Path

import param

from .model_base import Model
from ..ports import Ports
from .component_base import Component

class Element(Component):
    """Base class for all elements in the framework"""
    ports = param.ClassSelector(class_=Ports)

    def __init__(self, **params):
        super().__init__(**params)
        self.ports = Ports(containing_element=self)
    
    
    
    @staticmethod
    def port_emit(port_name: str):
        """
        Used to decorate a watch method so that when it runs, it emits
        the port labelled with the port_name if the port is established. 
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if port_name in self.ports.output:
                    self.ports.output[port_name].emit()
                else:
                    raise ValueError(f"Port {port_name} not found")
                return
            return wrapper
        return decorator

    @staticmethod
    def port_stage(port_name: str, model_param_name: str):
        """
        Used to decorate a watch method so that when it runs, it stages a
        model parameter on a port if both are established.
        model_param_name must match the name of the staged 
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if (model_param := getattr(self.model, model_param_name)):
                    if port_name in self.ports.output:
                        self.ports.output[port_name].stage(**{model_param_name: model_param})
                    else:
                        raise ValueError(f"Port {port_name} not found")
                else:
                    raise ValueError(f"Model parameter {model_param_name} not found")
                return
            return wrapper
        return decorator
    
    @staticmethod
    def port_stage_emit(port_name: str, model_param_name: str):
        """
        Used to decorate a watch method and emit the port labelled with the
        port_name if the port is established. 
        """
        def decorator(func):
            def wrapper(self, *args, **kwargs):
                func(self, *args, **kwargs)
                if (model_param := getattr(self.model, model_param_name)):
                    if port_name in self.ports.output:
                        self.ports.output[port_name].stage_emit(**{model_param_name: model_param})
                    else:
                        raise ValueError(f"Port {port_name} not found")
                else:
                    raise ValueError(f"Model parameter {model_param_name} not found")
                return
            return wrapper
        return decorator
