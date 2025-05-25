"""Recipe commands for Pyllments CLI."""
import typer
from rich.console import Console
from rich.table import Table
from inspect import Parameter, Signature
from typing import Optional, Any, List, Annotated

from pyllments.recipes import discover_recipes, run_recipe
from pyllments.logging import logger
from pyllments.cli.serve_helper import CommonOptions, FieldConfigProcessor, CommandRegistrar

app = typer.Typer(help="Manage and run Pyllments recipes")

@app.command("list")
def list_recipes():
    """List all available recipes."""
    recipes = discover_recipes()
    if not recipes:
        typer.echo("No recipes found.")
        raise typer.Exit()

    table = Table(title="Available Recipes")
    table.add_column("Recipe", style="cyan")
    table.add_column("Description")
    table.add_column("Configuration Arguments", style="green")

    for name, metadata in recipes.items():
        # Handle None docstring case
        docstring = metadata.get("docstring") or ""
        description = docstring.split("\n")[0] if docstring else "No description available"
        config_args = []
        if config := metadata.get("config"):
            config_args = list(config.get("fields", {}).keys())
        config_str = ", ".join(config_args) if config_args else "None"
        table.add_row(name, description, config_str)

    console = Console()
    console.print(table)
    console.print(
        "\nUse 'pyllments recipe run <recipe-name> --help' to see configuration options",
        style="dim"
    )

# Subgroup for run
run_app = typer.Typer(help="Run a Pyllments recipe")
app.add_typer(run_app, name="run")

def recipe_command_handler(**command_args):
    """
    Handle recipe command execution with consolidated argument processing.
    
    This function is called by the CommandRegistrar for each recipe command.
    """
    command_name = command_args['command_name']
    fields = command_args['fields']
    kwargs = command_args['kwargs']
    common_options = command_args['common_options']
    
    # Use CommonOptions for consolidated argument handling
    common_args = common_options.extract_common_args(kwargs)
    
    # Extract recipe-specific config
    recipe_config = {
        field_name: kwargs.get(field_name)
        for field_name in fields.keys()
        if field_name in kwargs
    }

    # Filter out 'profile' from common_args since run_recipe doesn't accept it
    run_recipe_args = {k: v for k, v in common_args.items() if k != 'profile'}

    # Execute recipe with profiling using consolidated utility
    common_options.execute_with_profiling(
        common_args,
        run_recipe,
        recipe_name=command_name,
        config=recipe_config,
        **run_recipe_args
    )

# Register commands dynamically using the consolidated registrar
common_options = CommonOptions()
for recipe_name, metadata in discover_recipes().items():
    CommandRegistrar.register_dynamic_command(
        app=run_app,
        command_name=recipe_name,
        metadata=metadata,
        command_func=recipe_command_handler,
        common_options=common_options
    ) 