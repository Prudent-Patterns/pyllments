"""Shared state for CLI components."""
import typer

app = typer.Typer(no_args_is_help=True)
recipe_app = typer.Typer(help="Run pre-built Pyllments recipes")
app.add_typer(recipe_app, name="recipe") 