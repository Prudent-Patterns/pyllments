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
    _watchers = param.Dict(default={}, doc="""
        Registry for watchers to prevent duplicates.""")

    def __init__(self, **params):
        self.id = str(uuid4())
        known_params = {k: v for k, v in params.items() if k in self.param}
        super().__init__(**known_params)
        

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
        """
        Decorator for Component view methods that handles CSS loading, sizing,
        and Panel parameters.

        This decorator provides several key functionalities:

        - Automatic loading and caching of CSS files associated with the view.
        - Merging of default function parameters with user-provided overrides.
        - Splitting of keyword arguments into:
            • Panel parameters: e.g., 'width', 'height', 'margin', etc., used by Panel
              to control the layout of components.
              **Note:** Any Panel parameter that is explicitly set to `None` is filtered out,
              ensuring that only defined values override Panel's default responsive behavior.
            • Custom attributes: All additional parameters that are not recognized as Panel parameters.
        - Applying the filtered Panel parameters to the created view after its instantiation.

        **Important:**
        Parameters such as `height` or `width` will only affect the view if they are explicitly set.
        If they are passed as `None`, they are ignored, allowing Panel's default behavior
        (for example, "stretch_both") to take effect.

        **Caching Behavior:**
        The decorated view is not automatically stored as a special Panel parameter or persistent attribute.
        The decorator checks for an existing view attribute (e.g., `myview_view`) on the instance and returns it if found.
        However, if the view does not exist, it is created on demand and returned without being automatically assigned
        to the instance. If persistent caching is desired, the view should be explicitly assigned to the instance,
        for example: setattr(self, view_attr_name, view).

        Parameters
        ----------
        func : callable
            The view method to be decorated.

        Returns
        -------
        callable
            The wrapped view method with enhanced CSS, sizing, and parameter handling.

        Notes
        -----
        Parameter Handling:
            - Default parameters from the function signature are merged with provided kwargs.
            - Parameters are split into two categories:
                1. Panel parameters: Standard Panel object parameters (width, height, etc.)
                2. Custom attributes: All other parameters including CSS parameters.
            - Panel parameters are applied after view creation.
            - Custom attributes are passed to the view creation function.

        CSS Loading and Priority:
            1. Default view CSS (css/viewname.css):
                - Loaded automatically if exists.
                - Applied as the first stylesheet.
            2. Part-specific CSS (css/viewname_part.css):
                - Loaded for each parameter ending in '_css'.
                - Applied in order of parameter definition.
            3. User-provided CSS:
                - Passed via '_css' parameters.
                - Can be string or list of strings.
                - Appended after corresponding file-based CSS.
            4. Developer stylesheets:
                - Passed via 'stylesheets' parameter.
                - Takes priority and is applied last.

        CSS File Structure:
            css/
            ├── viewname.css           # Default CSS for the entire view.
            ├── viewname_button.css    # CSS for button parts.
            └── viewname_input.css     # CSS for input parts.

        Examples
        --------
...     @view
...     def create_main(self, button_css=None, input_css=['custom.css'], stylesheets=None):
...         '''
...         CSS Priority:
...         1. main.css (if exists)
...         2. main_button.css + button_css parameter.
...         3. main_input.css + ['custom.css']
...         4. Developer stylesheets (highest priority)
...         '''
...         return pn.Column()
...
...     @view
...     def create_button(self, width=100, height=30, custom_attr='value', stylesheets=None):
...         '''
...         - width, height → Panel parameters (sizing_mode='fixed').
...         - custom_attr → Passed to view creation.
...         - stylesheets → Applied with highest priority.
...         '''
...         return pn.widgets.Button()

        See Also
        --------
        param.Parameterized : Base class for parameterized objects.
        panel.viewable.Viewable : Base class for Panel viewable objects.
        """
        PANEL_PARAMS = {
            'width', 'height', 'min_width', 'max_width', 'min_height', 'max_height',
            'margin', 'sizing_mode', 'aspect_ratio', 'align',
            'css_classes', 'styles', 'disabled', 'name', 'visible', 'design'
        }
        
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Use element's bound logger if available, otherwise fall back to default logger
            element_logger = getattr(self, 'logger', logger)
            
            # Get method signature parameters and their defaults
            sig = inspect.signature(func)
            sig_params = sig.parameters
            
            # Merge default values with provided kwargs
            defaults = {
                name: param.default 
                for name, param in sig_params.items() 
                if param.default is not inspect.Parameter.empty
            }
            merged_kwargs = {**defaults, **kwargs}

            view_name = func.__name__.replace('create_', '')
            
            # Proceed with creation...
            element_logger.debug(f"Creating new view for {view_name}")

            # Initialize CSS cache for this view if needed
            if view_name not in self.css_cache:
                self.css_cache[view_name] = {}

            # Extract developer stylesheets before splitting parameters
            developer_stylesheets = merged_kwargs.get('stylesheets', None)

            # Split kwargs into Panel params and custom attributes early
            # Panel params are either in PANEL_PARAMS or defined in the signature
            panel_kwargs = {k: v for k, v in merged_kwargs.items() if k in PANEL_PARAMS and v is not None}
            custom_attrs = {k: v for k, v in merged_kwargs.items() 
                          if k not in PANEL_PARAMS}

            # Remove stylesheets from custom_attrs if it's not in the function signature
            # This prevents passing stylesheets to functions that don't accept it
            if 'stylesheets' in custom_attrs and 'stylesheets' not in sig_params:
                del custom_attrs['stylesheets']

            # Process _css arguments first
            css_kwargs = [param for param in inspect.signature(func).parameters 
                         if param.endswith('_css')]
            
            element_logger.trace(f"CSS kwargs found in {func.__name__}: {css_kwargs}")
            
            # First load all potential CSS files for this view
            for key in css_kwargs:
                css_name = key[:-4]
                if css_name not in self.css_cache[view_name]:
                    # Get the css folder path
                    css_folder = self._get_module_path() / 'css'
                    css_file_path = css_folder / f"{view_name}_{css_name}.css"
                    element_logger.trace(f"Looking for component CSS file: {css_file_path}")
                    try:
                        with open(css_file_path, 'r') as f:
                            self.css_cache[view_name][css_name] = f.read()
                            element_logger.trace(f"Loaded component CSS from {css_file_path}")
                    except FileNotFoundError:
                        element_logger.trace(f"Component CSS file not found: {css_file_path}")
                        self.css_cache[view_name][css_name] = ''
                    except Exception as e:
                        element_logger.warning(f"Error loading CSS: {str(e)}")
                        self.css_cache[view_name][css_name] = ''

            # Now handle the CSS parameters
            for key in css_kwargs:
                css_name = key[:-4]
                # Get the default value for this parameter
                default_value = defaults.get(key, [])
                # Start with component CSS if it exists
                css_list = []
                if self.css_cache[view_name][css_name]:
                    css_list.append(self.css_cache[view_name][css_name])
                # Add any passed CSS
                if key in kwargs:
                    passed_css = kwargs[key]
                    if isinstance(passed_css, list):
                        css_list.extend(passed_css)
                    else:
                        css_list.append(passed_css)
                # Update the custom_attrs with the combined CSS
                custom_attrs[key] = css_list

            element_logger.trace(f"Final CSS kwargs: {[(k,v) for k,v in custom_attrs.items() if k.endswith('_css')]}")

            # Handle sizing mode
            has_height = 'height' in panel_kwargs
            has_width = 'width' in panel_kwargs
            if 'sizing_mode' not in panel_kwargs:
                if has_height and has_width:
                    panel_kwargs['sizing_mode'] = 'fixed'
                elif has_height:
                    panel_kwargs['sizing_mode'] = 'stretch_width'
                elif has_width:
                    panel_kwargs['sizing_mode'] = 'stretch_height'
                else:
                    panel_kwargs['sizing_mode'] = 'stretch_both'

            # Create view with function parameters only
            view = func(self, *args, **custom_attrs)
            
            # Apply Panel parameters to the returned view (except stylesheets, handled below)
            for param_name, param_value in panel_kwargs.items():
                if param_name != 'stylesheets':
                    setattr(view, param_name, param_value)
            
            # Default view CSS file check (no warning needed if not found)
            if 'default' not in self.css_cache[view_name]:
                css_folder = self._get_module_path() / 'css'
                css_file_path = css_folder / f"{view_name}.css"
                try:
                    with open(css_file_path, 'r') as f:
                        self.css_cache[view_name]['default'] = f.read()
                except FileNotFoundError:
                    self.css_cache[view_name]['default'] = ''
                except Exception as e:
                    element_logger.warning(f"Error loading CSS: {str(e)}")
                    self.css_cache[view_name]['default'] = ''

            # Build the final stylesheets list with proper priority
            final_stylesheets = []
            
            # 1. Add default view CSS if it exists (lowest priority)
            if self.css_cache[view_name]['default']:
                final_stylesheets.append(self.css_cache[view_name]['default'])
            
            # 2. Add any existing stylesheets from the view
            current_stylesheets = getattr(view, 'stylesheets', [])
            if current_stylesheets:
                if isinstance(current_stylesheets, list):
                    final_stylesheets.extend(current_stylesheets)
                else:
                    final_stylesheets.append(current_stylesheets)
            
            # 3. Add developer-specified stylesheets (highest priority)
            if developer_stylesheets:
                if isinstance(developer_stylesheets, list):
                    final_stylesheets.extend(developer_stylesheets)
                else:
                    final_stylesheets.append(developer_stylesheets)
            
            # Apply the final stylesheets list
            if final_stylesheets:
                view.stylesheets = final_stylesheets

            # Apply custom attributes
            for attr, value in custom_attrs.items():
                setattr(view, attr, value)
            
            return view

        return wrapper
    
    def watch_once(self, callback, parameter_name, parameterized_class=None, **kwargs):
        """
        Set up a watcher only once for a given method and parameter.
        Automatically generates a unique key based on the *calling method*.
        By default, the watcher is set up for the model, but can be augmented
        by passing a parameterized class.
        """
        if parameterized_class is None:
            parameterized_class = self.model
        # Get the name of the calling method (e.g., 'create_chatfeed_view')
        caller = inspect.currentframe().f_back.f_code.co_name
        # Create a unique key combining the method name and parameter
        key = f"{caller}_{parameter_name}"
        # Only set up the watcher if it doesn't already exist
        if key not in self._watchers:
            watcher = parameterized_class.param.watch(callback, parameter_name, **kwargs)
            self._watchers[key] = watcher
