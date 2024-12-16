import functools
from importlib.util import spec_from_file_location, module_from_spec
import inspect
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import panel as pn
from panel.io.fastapi import add_application
from uvicorn import run as uvicorn_run

from pyllments.common.registry import AppRegistry
from pyllments.logging import setup_logging, logger

def server_setup(): 
    setup_logging(log_file='file_loader.log', stdout_log_level='INFO', file_log_level='INFO')
    pn.config.css_files = ['assets/file_icons/tabler-icons-outline.min.css']
    pn.config.global_css = [
        """
    @import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:ital,wght@0,100..900;1,100..900&family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap');
    body {
        --primary-background-color: #0C1314;
        --secondary-background-color: #111926;
        --light-outline-color: #455368;
        --primary-accent-color: #D33A4B;
        --secondary-accent-color: #EDB737;
        --tertiary-accent-color: #12B86C;
        --white: #F4F6F8;
        --black: #353839;
        --faded-text-color: #6083B8;

        --base-font: 'Hanken Grotesk', sans-serif;
        --bokeh-base-font: 'Hanken Grotesk', sans-serif;
        --bokeh-font-size: 16px;
        --line-height: 1.55;
        --design-background-text-color: var(--white);

        
        background-color: var(--primary-background-color);
        /* Centering Body */
        display: flex;
        justify-content: center;
        align-items: center;
    }
    """
    ]

@logger.catch
def serve(filename: str=None, inline: bool=True):
    """
    Serves a Pyllments application either from a file or from the calling module.
    
    Parameters
    ----------
    filename : str, optional
        Path to the Python file containing the flow-decorated function
    inline : bool, default=True
        If True, looks for flow-decorated functions in the calling module
        If False, loads the function from the specified file
    """
    server_setup()
    
    try:
        app = AppRegistry.get_app()
    except Exception as e:
        logger.error(f"Failed to get FastAPI app: {e}")

    try:
        app.mount('/assets', StaticFiles(directory='/workspaces/pyllments/pyllments/assets'), name='assets')
    except Exception as e:
        logger.error(f"Failed to mount static files: {e}")

    def view_check(obj):
        return inspect.isfunction(obj) and hasattr(obj, 'contains_view')
    
    func_list = []
    if not inline:
        if not filename:
            raise ValueError("filename must be provided when inline=False")
        try:
            spec = spec_from_file_location('loaded_module', filename)
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            func_list = inspect.getmembers(module, view_check)
        except Exception as e:
            logger.error(f"Failed to load module from file {filename}: {e}")
            raise
    else:
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

    if len(func_list) > 1:
        logger.warning('Multiple flow wrapped functions found in script, using first found')
    elif len(func_list) == 1:
        name, obj = func_list[0]
        @add_application('/', app=app, title='Pyllments')
        def serve_gui():
            return obj()

    uvicorn_run(app, host='0.0.0.0', port=8000)


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


