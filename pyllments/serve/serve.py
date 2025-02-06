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
from pyllments.common.resource_loader import get_asset
from .registry import AppRegistry

ASSETS_PATH = 'assets'
ASSETS_MOUNT_PATH = f'/{ASSETS_PATH}'
FILE_ICONS_MOUNT_PATH = f'{ASSETS_MOUNT_PATH}/file_icons/tabler-icons-outline.min.css'
GLOBAL_CSS_MOUNT_PATH = f'{ASSETS_MOUNT_PATH}/css/global.css'

MAIN_TEMPLATE_PATH = 'templates/main.html'


def parse_dict_value(value):
    """
    Convert a string representation of a dictionary to a Python dictionary using ast.literal_eval.
    If the value is already a dict, return it unchanged.

    Parameters
    ----------
    value : str or dict
        The value to parse.

    Returns
    -------
    dict
        The parsed dictionary.

    Raises
    ------
    ValueError
        If the provided literal is not a valid dictionary.
    """
    if isinstance(value, dict):
        return value
    try:
        result = ast.literal_eval(value)
        if not isinstance(result, dict):
            raise ValueError("Provided literal is not a dictionary")
        return result
    except Exception as e:
        raise ValueError(f"Invalid dictionary literal: {value}. Error: {e}")


def server_setup(logging: bool = False, logging_level: str = 'INFO'): 
    if logging:
        setup_logging(log_file='file_loader.log', stdout_log_level=logging_level, file_log_level=logging_level)
    pn.config.css_files = [GLOBAL_CSS_MOUNT_PATH, FILE_ICONS_MOUNT_PATH]


def extract_config_class(filename: str) -> Optional[Dict]:
    """Extract Config class information from a file without executing it.
    
    Parameters
    ----------
    filename : str
        Path to the Python file.
        
    Returns
    -------
    Optional[Dict]
        If a Config class decorated as a dataclass is found, returns a dictionary with its
        docstring and fields (each with a default and type info).
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
                                    'default': item.value.value if isinstance(item.value, (ast.Num, ast.Str)) else None,
                                    'type': ast.unparse(item.annotation) if item.annotation is not None else 'str'
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
         
         # Ensure that dictionary fields are properly parsed.
         dict_fields = {
             name for name, info in config_info['fields'].items()
             if info.get("type", "str").lower().startswith("dict")
         }
         for key in dict_fields:
             if key in config_dict and not isinstance(config_dict[key], dict):
                 try:
                     config_dict[key] = parse_dict_value(config_dict[key])
                 except Exception as e:
                     logger.error(f"Failed to parse dictionary for field '{key}': {e}")
                     raise ValueError(f"Invalid dictionary literal for field '{key}': {config_dict[key]} Error: {e}")
         
         from dataclasses import make_dataclass
         # Map known type strings to actual Python types.
         type_mappings = {"int": int, "float": float, "bool": bool, "str": str}
         fields_list = []
         for field, info in config_info['fields'].items():
             field_type_str = info.get("type", "str")
             if field_type_str.lower().startswith("dict"):
                 field_type = parse_dict_value  # Use the conversion function as the field type.
             else:
                 field_type = type_mappings.get(field_type_str.lower(), str)
             default_value = info.get("default")
             fields_list.append((field, field_type, default_value))
         ConfigDynamic = make_dataclass("ConfigDynamic", fields_list)
         config_instance = ConfigDynamic(**config_dict)
    else:
         config_instance = config if config is not None else {}

    # Ensure that the configuration is available in the module's globals BEFORE executing the module.
    module.config = config_instance
    
    print(f"Executing module {module_name} with config {module.config}")
    spec.loader.exec_module(module)
    return module


def flow(func):
    """
    A decorator that adds the contains_view attribute to the function and wraps it.
    It is used to indicate that the function being wrapped returns a view and can be
    served as a GUI.
    """
    func.contains_view = True
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def serve(
    filename: str = None,
    inline: bool = False,
    logging: bool = False,
    logging_level: str = 'INFO',
    env: str = None,
    host: str = '0.0.0.0',
    port: int = 8000,
    find_gui: bool = True,
    config: Optional[Dict[str, Any]] = None
):
    """
    Serves a Pyllments application either from a file or from the calling module.
    
    Parameters
    ----------
    filename : str, optional
        Path to the Python file containing the flow-decorated function
    inline : bool, default=False
        If True, looks for flow-decorated functions in the calling module.
        If False, loads the function from the specified file.
    logging : bool, optional
        Enable logging, by default False.
    logging_level : str, optional
        Set logging level, by default 'INFO'.
    env : str, optional
        Path to .env file, by default None.
    host : str, default '0.0.0.0'
        The network interface to bind the server to. '0.0.0.0' means all interfaces.
    port : int, optional
        Port to run server on, by default 8000.
    find_gui : bool, optional
        Whether to look for GUI components, by default True.
    config : Optional[Dict[str, Any]], optional
        Configuration parameters to pass to the flow function, by default None.
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
        with resources.files('pyllments').joinpath(ASSETS_PATH) as f:
            app.mount(ASSETS_MOUNT_PATH, StaticFiles(directory=f), name=ASSETS_PATH)
    except Exception as e:
        logger.error(f"Failed to mount static files: {e}")

    if find_gui:
        def view_check(obj):
            return inspect.isfunction(obj) and hasattr(obj, 'contains_view')
        
        func_list = []
        if not inline:
            if not filename:
                raise ValueError("filename must be provided when inline=False")
            try:
                module = load_module_with_config('loaded_module', filename, config)
                func_list = inspect.getmembers(module, view_check)
            except Exception as e:
                logger.error(f"Failed to load module from file {filename}: {e}")
                raise
        else:
            frame = sys._getframe(1)
            while frame:
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
                with resources.files('pyllments').joinpath(MAIN_TEMPLATE_PATH) as f:
                    main_tmpl_str = f.read_text()
                tmpl = pn.Template(main_tmpl_str)
                tmpl.add_variable('app_favicon', ASSETS_MOUNT_PATH + '/favicon.ico')
                tmpl.add_panel('app_main', obj())
                return tmpl

    uvicorn_run(app, host=host, port=port)
