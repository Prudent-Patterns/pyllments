from pathlib import Path
from functools import wraps
import inspect
from typing import Callable

import param
from loguru import logger

from ..ports import Ports
from .component_base import Component

class Element(Component):
    """Base class for all elements in the framework"""
    ports = param.ClassSelector(class_=Ports, doc="""
        Handles the Port interface for the Element""")
    css_cache = param.Dict(default={}, instantiate=False, per_instance=False, doc="""
        Cache for CSS files - Set on the Class Level""")
    view_cache = param.Dict(default={}, doc="""
        Cache for views - Set on the Instance Level""")
    payload_css_cache = param.Dict(default={}, doc="""
        Cache for CSS files - Set on the Class Level
        Structure: payload_name: {}""")

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
    
    def inject_payload_css(self, create_view_method: Callable, name=None, **kwargs):
        """
        Used to wrap and run a create_*_view method of a Payload subclass in order
        to insert custom CSS from the Element's CSS folder into the kwargs
        of the view creation method.
        e.g. self.inject_payload_css(some_payload.create_custom_view)
        The name argument is used if the Element needs to style more than
        one *variety* of Payload.
        payload_css_cache is a dictionary that stores the CSS for each of
        the specified payload names (if provided). It is used to cache
        CSS so that it doesn't have to be loaded from the disk for each
        view creation method.
        If name remains None, the default key is just 'default'.
        Otherwise, the key is set as the name provided as one of the kwargs
        to the create_view_method.
        CSS is loaded from the Element's CSS folder, and has the pattern:
        "payload_{name}_{kwarg name without _css}.css". If the name kwarg
        isn't provided, just use the template "payload_{kwarg name without
        _css}.css".
        """
        sig = inspect.signature(create_view_method)
        css_kwargs = [param for param in sig.parameters if param.endswith('_css')]

        # Initialize payload_css_cache on the instance level
        if not hasattr(self, 'payload_css_cache'):
            self.payload_css_cache = {}

        cache_key = name or 'default'
        if cache_key not in self.payload_css_cache:
            self.payload_css_cache[cache_key] = {}

        for key in css_kwargs:
            css_name = key[:-4]  # Remove '_css' from the end
            if css_name not in self.payload_css_cache[cache_key]:
                module_path = type(self)._get_module_path()
                css_filename = f"payload_{name+'_' if name else ''}{css_name}.css"
                css_path = Path(module_path, 'css', css_filename)
                try:
                    with open(css_path, 'r') as f:
                        self.payload_css_cache[cache_key][css_name] = [f.read()]
                except FileNotFoundError:
                    logger.warning(f"CSS file not found: {css_path}")
                    self.payload_css_cache[cache_key][css_name] = ['']
                except Exception as e:
                    logger.warning(f"Error loading CSS: {str(e)}")
                    self.payload_css_cache[cache_key][css_name] = ['']

        # Prepare the kwargs with the loaded CSS
        for key in css_kwargs:
            if key not in kwargs or not kwargs[key]:
                css_name = key[:-4]
                kwargs[key] = self.payload_css_cache[cache_key][css_name]

        # Call the create_view_method and return the view
        return create_view_method(**kwargs)