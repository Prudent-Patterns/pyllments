"""Core CLI application and command grouping."""
import typer

# Import sub-command apps
from pyllments.cli.commands.serve import app as serve_app
from pyllments.cli.commands.recipe import app as recipe_app

app = typer.Typer(no_args_is_help=True)

# Register sub-commands
app.add_typer(serve_app, name="serve")
app.add_typer(recipe_app, name="recipe") 