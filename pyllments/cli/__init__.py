import typer
import cProfile
import pstats
from io import StringIO

from pyllments.serve import serve as serve_file
from pyllments.logging import logger


typer_app = typer.Typer(no_args_is_help=True)

@typer_app.command('serve')
def serve(
    filename: str, 
    logging: bool = False, 
    logging_level: str = 'INFO', 
    no_gui: bool = False, 
    port: int = 8000, 
    env: str = None,
    profile: bool = False
):
    """Start a Pyllments server.
    
    Args:
        filename: Path to the Python file containing the flow
        logging: Enable logging
        logging_level: Set logging level
        no_gui: Don't look for GUI components
        port: Port to run server on
        env: Path to .env file
        profile: Enable profiling output
    """
    logger.info(f"Starting Pyllments server for {filename}...")
    
    if profile:
        pr = cProfile.Profile()
        pr.enable()
        
    try:
        serve_file(filename=filename, inline=False, logging=logging, logging_level=logging_level, find_gui=not no_gui, port=port, env=env)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise  # Re-raise to show full traceback
    finally:
        if profile:
            pr.disable()
            s = StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)  # Print top 30 time-consuming functions
            print(s.getvalue())

@typer_app.callback()
def callback():
    """
    Pyllments CLI
    """
    pass