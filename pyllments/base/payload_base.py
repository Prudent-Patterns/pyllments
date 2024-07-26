from functools import wraps
from inspect import signature
from pathlib import Path
import warnings
import re

import param

from pyllments.base.component_base import Component

class Payload(Component):
    element_view_map = param.Dict(
        default={'default': {}}, per_instance=False, instantiate=True, doc="""
        A dictionary that stores the views for each element in the payload.
        The keys are the elements, and the values are dictionaries with the
        CSS for each individual Panel pane or widget defined in the Payload's
        create_*_view methods.
        Default key holds the default view and CSS when no element is passed.
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def view(cls, func):
        """
        Used to decorate the create_*_view methods for the purpose of
        populating the element_view_map with views pertaining to the calling
        element.
        The element is passed as the first argument to the decorated
        function in order to access the element's location and find the CSS in
        the CSS directory, and use the element_view_map as the cache to store
        the CSS as strings for each individual Panel pane or widget defined in
        the Payload's create_*_view methods.
        The Elements serve as keys in the element_view_map, and the values are
        the corresponding dictionaries which contain the CSS for each individual
        Panel pane or widget.
        There is also a 'default' key which holds the dictionary of the CSS for
        the panes and widgets found in the Payload's CSS directory.
        The name of the Payload view will be defined between the 'create_' and
        '_view' in the function name. That function takes as keyword arguments
        lists of CSS strings for each individual Panel pane or widget defined
        in the Payload's create_*_view methods.
        The pattern for the CSS files in the Element's CSS directory is the name
        of the Payload + _ + the name of the keyword argument in the function
        signature minus the '_css' suffix.
        To populate the keyword arguments(*_css), a list is passed to them of  
        with the value from the default dictionary for the Payload, followed by
        the value for the corresponding Element.
        """
        @wraps(func)
        def wrapper(self, element=None, *args, **kwargs):
            css_kwargs = [
                param for param
                in signature(func).parameters 
                if param.endswith('_css')
            ]
            
            for key in css_kwargs:
                if key not in self.element_view_map['default']:
                    payload_css = self._load_css(key[:-4], self._get_module_path())
                    self.element_view_map['default'][key] = payload_css

                if key not in kwargs or not kwargs[key]:
                    if element is not None:
                        if element not in self.element_view_map:
                            self.element_view_map[element] = {}
                        
                        element_css = self._load_css(
                            f"{self.__class__.__name__.lower()}_{key[:-4]}", 
                            element._get_module_path()
                        )
                        self.element_view_map[element][key] = element_css
                        kwargs[key] = [self.element_view_map['default'][key], element_css]
                    else:
                        kwargs[key] = [self.element_view_map['default'][key]]

            # Remove 'element' from kwargs to avoid passing it twice
            kwargs.pop('element', None)
            
            # Call the original function and get the view
            view = func(self, *args, **kwargs)
            
            # Store the view in the element_view_map
            if element is not None:
                view_name = re.search(r'create_(.+)_view', func.__name__).group(1)
                self.element_view_map[element]['view'] = view
            
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