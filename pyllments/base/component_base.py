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
    css_cache = param.Dict(default={})

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
        """
        Handles the CSS loading logic for view creation within components.
        Reliant on the existence of a CSS folder in the module's directory.
        Used to decorate a method that creates a view:
            @view
            def create_some_view(self, some_panel_css, another_panel_css):
                ...

        When the *_css arguments are None, the CSS is loaded from the CSS folder.
        Populates the _css_cache dictionary for the class with the CSS for the view:
            {
                'some_panel_css': '...',
                'another_panel_css': '...'
            }
        This is to prevent the CSS from being loaded multiple times.
        However, when CSS string arguments are passed to the create_*_view method,
        they are not added to the _css_cache dictionary, as they are meant to be
        for a custom usecase.
        In the event that the user needs to set custom CSS for _ALL_ instances of an
        Element, then they can set the CSS on the class itself:
            Component._css_cache['some_panel_css'] = '...'
        """
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
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
                    if key not in self.css_cache:
                        module_path = cls._get_module_path()
                        css_filename = Path(
                            module_path, 'css',
                            f'{key.replace("_css", ".css")}')
                        with open(css_filename, 'r') as f:
                            self.css_cache[key] = f.read()
                            return_kwargs[key] = self.css_cache[key]
                    else:
                        return_kwargs[key] = self.css_cache[key]
        
            return func(self, *args, **return_kwargs)
        return wrapper