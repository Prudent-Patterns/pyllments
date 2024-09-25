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

    def __init__(self, **params):
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
            # Get the view attribute name from the function name
            view_attr_name = func.__name__.replace('create_', '') + '_view'
            # The expected class is checked due to Row and Column layouts using __len__ in if statements
            if hasattr(self, view_attr_name):
                existing_view = getattr(self, view_attr_name)
                expected_class = self.param[view_attr_name].class_
                if isinstance(existing_view, expected_class):
                    warnings.warn(f'{view_attr_name} already exists. Returning existing view.')
                    return existing_view

            # If the view doesn't exist, proceed with CSS loading and view creation
            view_name = func.__name__.replace('create_', '')

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

            return func(self, *args, **kwargs)

        return wrapper