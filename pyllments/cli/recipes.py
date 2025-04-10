"""Recipe Command Creation and Discovery
===========================================

This module is responsible for discovering and registering recipes as dynamic CLI
commands for the Pyllments framework. A recipe is a pre-built workflow defined in a Python
file. The framework extracts metadata (such as docstrings and configuration options specified
via a dataclass 'Config') to automatically create Typer commands that execute the recipes.

Usage Examples:
---------------
To list all available recipes:
    $ pyllments recipe list

To run a recipe called "example_recipe" with default options:
    $ pyllments recipe run example_recipe

To run a recipe with additional configuration options:
    $ pyllments recipe run example_recipe --logging True --port 8080 --custom_option value

The automatically generated commands allow developers to quickly experiment with different
workflows and configurations.
"""

import ast
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

import typer
from pyllments.logging import logger
from pyllments.recipes.runner import run_recipe
from .state import recipe_app
from pyllments.recipes.discovery import get_recipe_metadata


def create_recipe_command(recipe_name: str, metadata: Dict) -> None:
    """Create a Typer command for a recipe using its metadata."""
    # Use the module docstring if available, otherwise generate a default help text.
    help_text = metadata.get('docstring') or f"Run the {recipe_name} recipe"
    # Generate a description using the Config class docstring, if available.
    config_doc = metadata.get('config', {}).get('docstring', '')
    if config_doc:
        help_text += f"\n\n{config_doc}"
    
    # Add help text for individual config fields if available.
    config_fields = metadata.get('config', {}).get('fields', {})
    if config_fields:
        help_text += "\n\nConfiguration Options:"
        for field_name, field_info in config_fields.items():
            field_help = field_info.get('metadata', {}).get('help', 'No description')
            help_text += f"\n  --config {field_name}=<value>  : {field_help}"

    @recipe_app.command(name=recipe_name.replace('_', '-'), help=help_text)
    def recipe_command(
        logging: bool = typer.Option(False, help="Enable logging"),
        logging_level: str = typer.Option("INFO", help="Set logging level"),
        no_gui: bool = typer.Option(False, help="Don't look for GUI components"),
        port: int = typer.Option(8000, help="Port to run server on"),
        env: Optional[str] = typer.Option(None, help="Path to .env file"),
        host: str = typer.Option(
            "127.0.0.1",
            "--host",
            "-H",
            help=("Network interface to bind the server to. "
                  "Defaults to 127.0.0.1 for local development.")
        ),
        profile: bool = typer.Option(False, help="Enable profiling output"),
        config: List[str] = typer.Option(
            [],
            help="Additional configuration options as key=value pairs"
        )
    ):
        # Combine key=value pairs into a configuration dictionary.
        config_dict = {}
        for pair in config:
            try:
                key, value = pair.split("=", 1)
            except ValueError:
                raise typer.BadParameter(
                    f"Configuration option '{pair}' is not in key=value format."
                )
            config_dict[key] = value

        if profile:
            import cProfile, pstats
            from io import StringIO
            pr = cProfile.Profile()
            pr.enable()

        try:
            run_recipe(
                recipe_name=recipe_name,
                logging=logging,
                logging_level=logging_level,
                no_gui=no_gui,
                port=port,
                env=env,
                host=host,
                config=config_dict
            )
        except Exception as e:
            logger.error(f"Failed to run recipe {recipe_name}: {str(e)}")
            raise
        finally:
            if profile:
                pr.disable()
                s = StringIO()
                ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
                ps.print_stats(30)
                print(s.getvalue())


def discover_recipes():
    """Discover and create commands for all available recipes."""
    # Locate the base 'recipes' directory where this cli/recipes.py resides
    # then navigate to the 'available_recipes' subdirectory.
    available_recipes_dir = Path(__file__).parent.parent / 'recipes' / 'available_recipes'
    
    # Look for recipe modules within the 'available_recipes' directory
    for recipe_path in available_recipes_dir.glob('**/[!_]*.py'):
        # Skip the helper modules like runner.py or discovery.py if they exist here
        if recipe_path.stem not in ['discovery', 'runner']:
            if metadata := get_recipe_metadata(recipe_path):
                create_recipe_command(recipe_path.stem, metadata)


__all__ = ['discover_recipes'] 
