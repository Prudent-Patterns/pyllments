from functools import wraps
from inspect import signature
from pathlib import Path
import warnings
import re

import param

from pyllments.base.component_base import Component

class Payload(Component):
    css_cache = param.Dict(default={}, doc="""
        Cache for CSS files - Set on the Class Level""")
    view_cache = param.Dict(default={}, doc="""
        Cache for views - Set on the Instance Level""")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def view(cls, func):
        """
        The view decorator is a class method that is used to wrap view creation functions within the Payload class.
        It provides caching mechanisms for CSS stylesheets and the generated views to enhance performance and 
        reduce redundant computations.

        Usage:
        - This decorator should be applied to methods that create views for the Payload class. The method name 
          should follow the convention of 'create_<view_name>_view' to ensure proper functionality.
        - When the decorated method is called, the decorator checks if the required CSS files are already cached.
          If not, it attempts to load them from the appropriate directory. If the CSS file is not found, a warning 
          is issued, and an empty string is used instead.
        - The decorator also checks if the view has already been created and cached. If it has, the cached view 
          is returned immediately, avoiding unnecessary re-creation.
        - If the view is not cached, the original method is called to create the view, which is then stored in 
          the cache for future use.

        Parameters:
        - func: The function to be decorated, which should create and return a view.

        Returns:
        - A wrapper function that manages the caching of CSS and views.

        Example:
        @Payload.view
        def create_custom_view(self, custom_css='', **kwargs):
            # Implementation for creating a custom view
            pass
        """
        
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            sig = signature(func)
            css_kwargs = [param for param in sig.parameters if param.endswith('_css')]

            for key in css_kwargs:
                view_name = re.search(r'create_(.+)_view', func.__name__).group(1)
                cache_key = f"{view_name}_{key[:-4]}"
                if key not in kwargs or not kwargs[key]:
                    if cache_key not in type(self).css_cache:
                        module_path = type(self)._get_module_path()
                        css_filename = Path(module_path, 'css', f'{key[:-4]}.css')
                        try:
                            with open(css_filename, 'r') as f:
                                type(self).css_cache[cache_key] = [f.read()]
                        except FileNotFoundError:
                            warnings.warn(f"CSS file not found: {css_filename}")
                            type(self).css_cache[cache_key] = ['']
                        except Exception as e:
                            warnings.warn(f"Error loading CSS: {str(e)}")
                            type(self).css_cache[cache_key] = ['']
                    kwargs[key] = type(self).css_cache[cache_key]

            # Check if the view is already cached
            if func.__name__ in self.view_cache:
                return self.view_cache[func.__name__]

            # Create the view and cache it
            view = func(self, *args, **kwargs)
            self.view_cache[func.__name__] = view
            return view
        return wrapper

    @staticmethod
    def _load_css(key, module_path):
        """Load CSS from a file, returning an empty string if not found."""
        css_path = Path(module_path, 'css', f'{key}.css')
        try:
            with css_path.open('r') as file:
                return file.read()
        except FileNotFoundError:
            warnings.warn(f"CSS file not found: {css_path}")
        except Exception as e:
            warnings.warn(f"Error loading CSS: {str(e)}")
        return ''