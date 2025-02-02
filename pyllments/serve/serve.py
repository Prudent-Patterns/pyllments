"""Core serve functionality."""
import functools
from importlib import resources
from importlib.util import spec_from_file_location, module_from_spec
import inspect
import sys
from typing import Optional, Dict, Any
import ast

from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
import panel as pn
from panel.io.fastapi import add_application
from uvicorn import run as uvicorn_run

from pyllments.logging import setup_logging, logger
from .registry import AppRegistry


def server_setup(logging: bool = False, logging_level: str = 'INFO'): 
    if logging:
        setup_logging(log_file='file_loader.log', stdout_log_level=logging_level, file_log_level=logging_level)
    pn.config.css_files = ['assets/file_icons/tabler-icons-outline.min.css']
    pn.config.global_css = [
        """
    @import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:ital,wght@0,100..900;1,100..900&family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap');
    body {
        --primary-background-color: #0C1314;
        --secondary-background-color: #162030;
        --light-outline-color: #455368;
        --primary-accent-color: #D33A4B;
        --secondary-accent-color: #EDB737;
        --tertiary-accent-color: #12B86C;
        --white: #F4F6F8;
        --black: #353839;
        --faded-text-color: #6083B8;

        --base-font: 'Hanken Grotesk', sans-serif;
        --bokeh-base-font: var(--base-font), sans-serif;
        --bokeh-font-size: 16px;
        --title-font: 'Ubuntu', sans-serif;
        --line-height: 1.55;
        --design-background-text-color: var(--white);
        --radius: 9px;
        
        background-color: var(--primary-background-color);
        /* Centering Body */
        display: flex;
        justify-content: center;
        align-items: center;    
    }
    h3 {
        font-family: var(--base-font);
    }
    """
    ]


def extract_config_class(filename: str) -> Optional[Dict]:
    """Extract Config class information from a file without executing it.
    
    Parameters
    ----------
    filename : str
        Path to the Python file.
        
    Returns
    -------
    Optional[Dict]
        If a Config class decorated as a dataclass is found, returns a dictionary with the following keys:
            'docstring': (str or None) The docstring of the Config class if available.
            'fields': (dict) A dictionary mapping each field name (str) to a sub-dictionary with:
                'default': The default value of the field if it is specified and is a basic type (number or string); otherwise, None.
        Returns None if no appropriate Config class is found.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
            
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Config':
                # Check if the class is decorated with @dataclass
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'dataclass':
                        return {
                            'docstring': ast.get_docstring(node),
                            'fields': {
                                item.target.id: {
                                    'default': item.value.value if isinstance(item.value, (ast.Num, ast.Str)) else None
                                }
                                for item in node.body
                                if isinstance(item, ast.AnnAssign) and hasattr(item, 'value')
                            }
                        }
        return None
    except Exception as e:
        logger.error(f"Failed to parse config from {filename}: {e}")
        return None


def load_module_with_config(module_name: str, filename: str, config: Optional[Dict[str, Any]] = None):
    """
    Load a module and make config available at module level.

    If the module has a Config class defined, this function will extract the configuration fields via AST,
    merge them with any provided configuration, and then inject the final config_dict into the module's
    globals before executing the module.

    Parameters
    ----------
    module_name : str
        Name to assign to the loaded module.
    filename : str
        The file path to the module.
    config : Optional[Dict[str, Any]], optional
        Configuration to use (overrides extracted defaults), by default None

    Returns
    -------
    module
        The loaded module with config injected into its globals.
    """
    spec = spec_from_file_location(module_name, filename)
    module = module_from_spec(spec)

    # Extract Config information from the module source code using AST.
    config_info = extract_config_class(filename)

    if config_info:
        # Build the configuration dictionary by favoring provided configuration values.
        config_dict = {}
        if config:
            for field_name, field_info in config_info['fields'].items():
                config_dict[field_name] = config.get(field_name, field_info.get('default'))
        else:
            config_dict = {
                name: info.get('default')
                for name, info in config_info['fields'].items()
            }
    else:
        config_dict = config if config is not None else {}

    # Ensure that the configuration is available in the module's globals during execution.
    module.config = config_dict
    print(f"Executing module {module_name} with config {config_dict}")
    # Execute the module with the modified globals.
    spec.loader.exec_module(module)
    return module


def flow(func):
    """A decorator that adds the contains_view attribute to the function and wraps it.
    It is used to indicate that the function being wrapped returns a view and can be
    served as a GUI.
    """
    func.contains_view = True
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def serve(
    filename: str=None,
    inline: bool=False,
    logging: bool=False,
    logging_level: str='INFO',
    env: str=None,
    port: int=8000,
    find_gui: bool=True,
    config: Optional[Dict[str, Any]]=None
    ):
    """
    Serves a Pyllments application either from a file or from the calling module.
    
    Parameters
    ----------
    filename : str, optional
        Path to the Python file containing the flow-decorated function
    inline : bool, default=True
        If True, looks for flow-decorated functions in the calling module
        If False, loads the function from the specified file
    logging : bool, optional
        Enable logging, by default False
    logging_level : str, optional
        Set logging level, by default 'INFO'
    env : str, optional
        Path to .env file, by default None
    port : int, optional
        Port to run server on, by default 8000
    find_gui : bool, optional
        Whether to look for GUI components, by default True
    config : Optional[Dict[str, Any]], optional
        Configuration parameters to pass to the flow function, by default None
    """
    server_setup(logging=logging, logging_level=logging_level)
    if env:
        load_dotenv(env)
    else:
        load_dotenv()
    try:
        app = AppRegistry.get_app()
    except Exception as e:
        logger.error(f"Failed to get FastAPI app: {e}")

    try:
        with resources.files('pyllments').joinpath('assets') as f:
            app.mount('/assets', StaticFiles(directory=f), name='assets')
    except Exception as e:
        logger.error(f"Failed to mount static files: {e}")

    if find_gui:
        def view_check(obj):
            return inspect.isfunction(obj) and hasattr(obj, 'contains_view')
        
        func_list = []
        # Use with `pyllments serve <filename>`
        if not inline:
            if not filename:
                raise ValueError("filename must be provided when inline=False")
            try:
                module = load_module_with_config('loaded_module', filename, config)
                func_list = inspect.getmembers(module, view_check)
            except Exception as e:
                logger.error(f"Failed to load module from file {filename}: {e}")
                raise
        elif inline:
            # Walk up the call stack to find the caller's frame
            frame = sys._getframe(1)
            while frame:
                # Check if we've found a module with flow-decorated functions
                module = sys.modules.get(frame.f_globals.get('__name__'))
                if module:
                    func_list = inspect.getmembers(module, view_check)
                    if func_list:
                        break
                frame = frame.f_back

        if func_list_len := len(func_list) >= 1:
            if func_list_len > 1:
                logger.warning(f'{func_list_len} @flow wrapped functions found in script, using first found')
            elif func_list_len == 1:
                logger.info(f"Found @flow wrapped function in script")
            name, obj = func_list[0]
            @add_application('/', app=app, title='Pyllments')
            def serve_gui():
                return obj()  # Config is already available at module level

    uvicorn_run(app, host='0.0.0.0', port=port)
