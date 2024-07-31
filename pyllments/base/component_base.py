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
        """Load CSS from the component's own CSS folder, cache it, and use it appropriately."""
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

            # Determine the CSS folder for the component
            css_folder = Path(self._get_module_path(), 'css')

            for key in css_kwargs:
                # Extract the CSS name by removing the '_css' suffix
                # Example: 'button_css' becomes '{view_name}_button'
                css_name = key[:-4]
                # Create the new CSS filename structure
                css_filename = f"{view_name}_{css_name}.css"
                
                # Load CSS from file if not in cache
                if css_name not in self.css_cache[view_name]:
                    css_file_path = css_folder / css_filename
                    try:
                        with open(css_file_path, 'r') as f:
                            # Store the loaded CSS in the cache
                            self.css_cache[view_name][css_name] = f.read()
                    except FileNotFoundError:
                        logger.warning(f"CSS file not found: {css_file_path}")
                        self.css_cache[view_name][css_name] = ''
                    except Exception as e:
                        logger.warning(f"Error loading CSS: {str(e)}")
                        self.css_cache[view_name][css_name] = ''

                # Get the cached CSS (which might be an empty string if no file was found)
                cached_css = self.css_cache[view_name][css_name]

                # Combine cached CSS with provided CSS
                if key in kwargs:
                    if isinstance(kwargs[key], list):
                        if cached_css:
                            kwargs[key] = [cached_css] + kwargs[key]
                    else:
                        kwargs[key] = [cached_css, kwargs[key]] if cached_css else [kwargs[key]]
                elif cached_css:
                    kwargs[key] = [cached_css]

            view = func(self, *args, **kwargs)
            self.view_cache[view_name] = view
            return view

        return wrapper