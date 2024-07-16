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
