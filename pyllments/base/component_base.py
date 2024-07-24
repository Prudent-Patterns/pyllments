import sys
import inspect
import warnings
import functools
from pathlib import Path

import param

from pyllments.base.model_base import Model


class Component(param.Parameterized):
    """Base class for all components(Elements and Payloads)"""
    model = param.ClassSelector(class_=Model)
    css_cache = param.Dict(default={}, doc="Cache for CSS files - Set on the Class Level")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    @classmethod
    def view(cls, func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            sig = inspect.signature(func)
            css_kwargs = [param for param in sig.parameters if param.endswith('_css')]

            for key in css_kwargs:
                if key not in kwargs or not kwargs[key]:
                    if key not in type(self).css_cache:
                        module_path = type(self)._get_module_path()
                        css_filename = Path(module_path, 'css', f'{key.replace("_css", ".css")}')
                        try:
                            with open(css_filename, 'r') as f:
                                type(self).css_cache[key] = f.read()
                        except FileNotFoundError:
                            warnings.warn(f"CSS file not found: {css_filename}")
                        except Exception as e:
                            warnings.warn(f"Error loading CSS: {str(e)}")
                    kwargs[key] = type(self).css_cache.get(key, '')

            return func(self, *args, **kwargs)
        return wrapper