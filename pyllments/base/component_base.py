import sys
import inspect
import re
import warnings
import functools
from pathlib import Path

import param

from pyllments.base.model_base import Model


class Component(param.Parameterized):
    """Base class for all components(Elements and Payloads)"""
    model = param.ClassSelector(class_=Model)
    _css_cache = param.Dict(default={})

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
    
    def load_css(self):
        css = type(self).get_method_name(prefix='create_', suffix='_view', level=2)
        if css not in type(self)._css_cache:
            module_path = self._get_module_path()
            css_filename = Path(module_path, 'css', f'{css}.css')
            with open(css_filename, 'r') as f:
                self._css_cache[css] = f.read()
        return self._css_cache[css_filename]

    def _view_exists(self, view):
        if view:
            warnings.warn(f'{view} already exists. Returning existing view.')
            return True
        
    @classmethod
    def get_method_name(cls, prefix: str = '', suffix: str = '', level: int = 1) -> str:
        """
        Get the name of the method at a specified level of nesting in the call stack, with
        optional prefix and suffix filtering.
        
        :param level: The level of nesting (1 for immediate caller, 2 for caller's caller, etc.)
        :param prefix: Optional prefix to filter the method name with
        :param suffix: Optional suffix to filter the method name with
        :return: The name of the method at the specified level, filtered by prefix and suffix if provided
        """

        frame = inspect.currentframe()
        try:
            for _ in range(level):
                frame = frame.f_back
            method_name = frame.f_code.co_name
            pattern = f'{re.escape(prefix)}(.*){re.escape(suffix)}'
            match = re.match(pattern, method_name)
            if match:
                return match.group(1)
            else:
                return method_name
        finally:
            del frame  # Avoid reference cycles    

    def view(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return_kwargs = {}
            # Get the function's parameter names
            sig = inspect.signature(func)
            css_kwargs = [param for param in sig.parameters if param.endswith('_css')]
            
            for key, val in kwargs.items():
                if (key in css_kwargs) and val:
                    return_kwargs[key] = val
                # When nothing is passed to the view creation method
                # Check CSS cache, if it's not in the cache, load it
                elif (key in css_kwargs) and (not val): 
                    if key not in self._css_cache:
                        module_path = type(self)._get_module_path()
                        css_filename = Path(
                            module_path, 'css',
                            f'{key.replace("_css", "")}.css')
                        with open(css_filename, 'r') as f:
                            self._css_cache[key] = f.read()
                            return_kwargs[key] = self._css_cache[key]
                    else:
                        return_kwargs[key] = self._css_cache[key]
        
            return func(**return_kwargs)
        return wrapper
