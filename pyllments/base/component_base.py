import sys
import inspect
import warnings
from functools import wraps
from pathlib import Path
from uuid import uuid4

import param
from loguru import logger

from pyllments.base.model_base import Model


class Component(param.Parameterized):
    """Base class for all components(Elements and Payloads)"""
    model = param.ClassSelector(class_=Model)
    id = param.String()
    css_cache = param.Dict(default={}, instantiate=False, per_instance=False, doc="""
        Cache for CSS files - Set on the Class Level""")
    view_cache = param.Dict(default={}, doc="""
        Cache for views - Set on the Instance Level""")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = str(uuid4())

    @classmethod
    def _get_module_path(cls):
        """
        Gets the path of the class's module in which it is defined.
        Gets the path of the child, not the parent class if the class is subclassed.
        """
        # Get the module where the class is defined
        module = sys.modules[cls.__module__]
        # Return the parent directory of the module's file
        return Path(module.__file__).parent

    def _view_exists(self, view):
        if view:
            warnings.warn(f'{view} already exists. Returning existing view.')
            return True
    
    def __hash__(self):
        """Return a hash of the component's id for use in hash-based collections."""
        return hash(self.id)

    def __eq__(self, other):
        """Check equality based on the component's id."""
        if not isinstance(other, Component):
            return NotImplemented
        return self.id == other.id
    @classmethod
    def view(cls, func):
        """Load CSS from the function signature, cache it, and cache the view."""
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Derive the view name from the function name by removing 'create_' prefix
            # Example: 'create_chat_view' becomes 'chat_view'
            view_name = func.__name__.replace('create_', '')

            # Check if the view is already cached using the derived view name
            if view_name in self.view_cache:
                return self.view_cache[view_name]

            sig = inspect.signature(func)
            # Identify parameters that end with '_css' to load corresponding CSS files
            css_kwargs = [param for param in sig.parameters if param.endswith('_css')]

            # Initialize the css_cache for this view if it doesn't exist
            if view_name not in self.css_cache:
                self.css_cache[view_name] = {}

            for key in css_kwargs:
                # Extract the CSS name by removing the '_css' suffix
                # Example: 'button_css' becomes 'button'
                css_name = key[:-4]  
                if css_name not in self.css_cache[view_name]:
                    module_path = self._get_module_path()
                    css_filename = Path(module_path, 'css', f'{css_name}.css')
                    try:
                        with open(css_filename, 'r') as f:
                            # Store the loaded CSS in the cache
                            self.css_cache[view_name][css_name] = f.read()
                    except FileNotFoundError:
                        logger.warning(f"CSS file not found: {css_filename}")
                        self.css_cache[view_name][css_name] = ''
                    except Exception as e:
                        logger.warning(f"Error loading CSS: {str(e)}")
                        self.css_cache[view_name][css_name] = ''

                # Ensure the CSS kwarg is a list and the default CSS is the first item
                if key not in kwargs or not kwargs[key]:
                    kwargs[key] = [self.css_cache[view_name][css_name]]
                elif isinstance(kwargs[key], list):
                    kwargs[key].insert(0, self.css_cache[view_name][css_name])
                else:
                    kwargs[key] = [self.css_cache[view_name][css_name], kwargs[key]]

            # Create the view using the original function and cache it
            view = func(self, *args, **kwargs)
            # Store the created view in the view_cache using the view_name
            self.view_cache[view_name] = view  # Store the view object directly
            return view

        return wrapper