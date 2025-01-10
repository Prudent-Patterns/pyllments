import typer

from pyllments.serve import serve as serve_file
from pyllments.logging import logger


typer_app = typer.Typer(no_args_is_help=True)

@typer_app.command('serve')
def serve(filename: str, logging: bool = False, no_gui: bool = False, port: int = 8000, env: str = None):
    logger.info(f"Starting Pyllments server for {filename}...")
    try:
        serve_file(filename=filename, inline=False, logging=logging, find_gui=not no_gui, port=port, env=env)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise  # Re-raise to show full traceback

@typer_app.callback()
def callback():
    """
    Pyllments CLI
    """
    pass