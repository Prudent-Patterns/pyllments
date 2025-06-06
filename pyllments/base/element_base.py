from pathlib import Path
from functools import wraps
import inspect
from typing import Callable

import param
from dotenv import load_dotenv
from loguru import logger

from pyllments.ports.ports import Ports
from pyllments.base.component_base import Component
from pyllments.base.model_base import Model

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
    name = param.String(doc="Unique name for this element instance")
    _instance_counters = {}  # class‐level dict to track counts per subclass
    env_path = param.String(default=None)

    _env_path = ''

    def __init__(self, **params):
        cls = type(self)
        count = cls._instance_counters.get(cls, 0) + 1
        cls._instance_counters[cls] = count

        # if developer passed a name, respect it; otherwise build one
        if 'name' not in params or not params['name']:
            params['name'] = f"{cls.__name__}{count}"
        super().__init__(**params)
        type(self).load_env(self.env_path)

        # bind logger so every message carries this name
        self.logger = logger.bind(name=self.__class__.__module__, element=self.name)
        self.ports = Ports(containing_element=self)

    def inject_payload_css(self, create_view_method: Callable, name=None, **kwargs):
        """Injects CSS from the Element's CSS folder into Payload view methods.

        This method wraps Payload view creation methods to automatically load and inject
        CSS from the Element's CSS directory. It supports both default view CSS and
        part-specific CSS files, with optional naming prefixes.

        Parameters
        ----------
        create_view_method : callable
            The Payload's view creation method to be wrapped
        name : str, optional
            Optional prefix for CSS file names, allowing multiple CSS sets
            for different instances of the same Payload type
        **kwargs
            Arguments to pass to the view creation method

        Returns
        -------
        panel.viewable.Viewable
            The created view with injected CSS

        Notes
        -----
        CSS File Loading Priority:
        1. Default view CSS file:
            - With name: payload_{name}_{view_name}.css
            - Without name: payload_{view_name}.css
        2. Part-specific CSS files (for each _css parameter):
            - With name: payload_{name}_{part}.css
            - Without name: payload_{part}.css
        3. User-provided CSS in kwargs

        CSS File Structure:
            css/
            ├── payload_main.css           # Default CSS for unnamed main view
            ├── payload_custom_main.css    # Default CSS for main view with name='custom'
            ├── payload_button.css         # CSS for unnamed button parts
            └── payload_custom_button.css  # CSS for button parts with name='custom'

        CSS Caching:
            - CSS files are cached at the instance level in payload_css_cache
            - Cache structure: {name: {view_name: {css_type: content}}}
            - Files are loaded only once per name/view combination

        Examples
        --------
        >>> class MyElement(Element):
        ...     def create_payload_view(self):
        ...         # Basic usage
        ...         return self.inject_payload_css(
        ...             payload.create_main
        ...         )
        ...
        ...     def create_named_payload_view(self):
        ...         # With name prefix and custom CSS
        ...         return self.inject_payload_css(
        ...             payload.create_main,
        ...             name='custom',
        ...             button_css=['additional.css']
        ...         )

        Warnings
        --------
        Logs a warning if no CSS files are found when the CSS directory exists
        and files were expected based on the view method's parameters.
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
            
            self.logger.warning(
                f"No CSS files found for {element_name}'s inject_payload_css call{name_str}. "
                f"Expected files in {module_path}/css/: {expected_files}"
            )
        
        return view

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # Automatically propagate the element's logger to its model
        if name == 'model' and isinstance(value, Model):
            model_logger = getattr(self, 'logger', None)
            if model_logger:
                value.logger = model_logger

    @classmethod
    def load_env(cls, path: str = None):
        if path:
            cls._env_path = path           
            load_dotenv(cls._env_path)
        else:
            cls._env_path = "."