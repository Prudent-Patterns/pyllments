import typer

from pyllments.serve import serve as serve_file


typer_app = typer.Typer(no_args_is_help=True)

@typer_app.command('serve')
def serve(filename: str, logging: bool = False):
    serve_file(filename=filename, inline=False, logging=logging)

@typer_app.callback()
def callback():
    """
    Pyllments CLI
    """
    pass