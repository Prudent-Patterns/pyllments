from pathlib import Path
from functools import wraps
import inspect
from typing import Callable

import param
from loguru import logger

from pyllments.ports.ports import Ports
from pyllments.base.component_base import Component

class Element(Component):
    """Base class for all elements in the framework"""
    ports = param.ClassSelector(class_=Ports, doc="""
        Handles the Port interface for the Element""")
    css_cache = param.Dict(default={}, instantiate=False, per_instance=False, doc="""
        Cache for CSS files - Set on the Class Level""")
    # view_cache = param.Dict(default={}, doc=""" TODO: Removeif no interference
    #     Cache for views - Set on the Instance Level""")
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
        Wraps payload view creation methods to inject CSS from the Element's CSS folder.
        
        Always looks for and applies a default view CSS file:
            - With name: payload_{name}_{view_name}.css
            - Without name: payload_{view_name}.css
        
        For each CSS kwarg (ending in _css), looks for:
            - With name: payload_{name}_{kwarg}.css
            - Without name: payload_{kwarg}.css
        
        Warns if no CSS files are found when using this method.
        """
        view_name = create_view_method.__name__.split('create_')[1]
        sig = inspect.signature(create_view_method)
        css_kwargs = [param for param in sig.parameters if param.endswith('_css')]
        
        # Get module path early
        module_path = type(self)._get_module_path()
        
        # Initialize cache
        cache_key = name or 'default'
        if cache_key not in self.payload_css_cache:
            self.payload_css_cache[cache_key] = {}
        if view_name not in self.payload_css_cache[cache_key]:
            self.payload_css_cache[cache_key][view_name] = {}
        
        # Track if any CSS files are found and which ones we tried to load
        css_files_found = False
        attempted_files = []
        
        # Load default view CSS
        if 'default' not in self.payload_css_cache[cache_key][view_name]:
            default_css_filename = f"payload_{name+'_' if name else ''}{view_name}.css"
            css_path = Path(module_path, 'css', default_css_filename)
            try:
                with open(css_path, 'r') as f:
                    self.payload_css_cache[cache_key][view_name]['default'] = f.read()
                    css_files_found = True
            except FileNotFoundError:
                self.payload_css_cache[cache_key][view_name]['default'] = ''
                attempted_files.append(default_css_filename)
        
        # Process CSS kwargs
        for key in css_kwargs:
            css_name = key[:-4]
            if key not in self.payload_css_cache[cache_key][view_name]:
                css_filename = f"payload_{name+'_' if name else ''}{css_name}.css"
                css_path = Path(module_path, 'css', css_filename)
                try:
                    with open(css_path, 'r') as f:
                        self.payload_css_cache[cache_key][view_name][key] = f.read()
                        css_files_found = True
                except FileNotFoundError:
                    self.payload_css_cache[cache_key][view_name][key] = ''
                    if Path(module_path, 'css').exists():  # Only track if CSS folder exists
                        attempted_files.append(css_filename)
            
            # Add cached CSS to kwargs if it exists
            if self.payload_css_cache[cache_key][view_name][key]:
                if key not in kwargs:
                    kwargs[key] = []
                if isinstance(kwargs[key], list):
                    kwargs[key] = [self.payload_css_cache[cache_key][view_name][key]] + kwargs[key]
                else:
                    kwargs[key] = [self.payload_css_cache[cache_key][view_name][key], kwargs[key]]
        
        # Create view with processed kwargs
        view = create_view_method(**kwargs)
        
        # Apply default view CSS if it exists
        default_css = self.payload_css_cache[cache_key][view_name]['default']
        if default_css:
            current_stylesheets = getattr(view, 'stylesheets', [])
            if isinstance(current_stylesheets, list):
                view.stylesheets = [default_css] + current_stylesheets
            else:
                view.stylesheets = [default_css, current_stylesheets]
        
        # Only warn if we actually tried to load files and none were found
        if not css_files_found and attempted_files and Path(module_path, 'css').exists():
            element_name = type(self).__name__
            name_str = f" with name='{name}'" if name else ""
            expected_files = " or ".join(attempted_files)
            
            logger.warning(
                f"No CSS files found for {element_name}'s inject_payload_css call{name_str}. "
                f"Expected files in {module_path}/css/: {expected_files}"
            )
        
        return view