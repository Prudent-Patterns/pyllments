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


@dataclass
class RecipeMetadata:
    """Metadata about a recipe extracted from its source code."""
    name: str
    path: Path
    docstring: Optional[str] = None
    config_class: Optional[Dict] = None


def extract_config_metadata(node: ast.ClassDef) -> Dict:
    """Extract metadata from a Config class definition.
    
    Parameters
    ----------
    node : ast.ClassDef
        The AST node for the Config class
        
    Returns
    -------
    Dict
        Dictionary containing the config class metadata
    """
    result = {
        'docstring': ast.get_docstring(node),
        'fields': {}
    }
    
    for item in node.body:
        if isinstance(item, ast.AnnAssign):  # This is a type-annotated field
            field_name = item.target.id
            
            # We only need to extract the help text and constraints from metadata
            if isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name) and item.value.func.id == 'field':
                field_data = {}
                for kw in item.value.keywords:
                    if kw.arg == 'metadata':
                        if isinstance(kw.value, ast.Dict):
                            metadata = {}
                            for k, v in zip(kw.value.keys, kw.value.values):
                                if isinstance(k, ast.Str):
                                    # Only extract help text and validation constraints
                                    if k.value in ('help', 'min', 'max', 'pattern'):
                                        metadata[k.value] = v.value
                            if metadata:
                                field_data['metadata'] = metadata
                result['fields'][field_name] = field_data
    
    return result


def get_recipe_metadata(recipe_path: Path) -> Optional[RecipeMetadata]:
    """Extract metadata from a recipe file without importing it.
    
    Parameters
    ----------
    recipe_path : Path
        Path to the recipe file
        
    Returns
    -------
    Optional[RecipeMetadata]
        Metadata about the recipe if successfully parsed
    """
    try:
        with open(recipe_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        metadata = RecipeMetadata(
            name=recipe_path.stem,
            path=recipe_path,
            docstring=ast.get_docstring(tree)
        )
        
        # Look for Config class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Config':
                # Check if it's a dataclass
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'dataclass':
                        metadata.config_class = extract_config_metadata(node)
                        break
        
        return metadata
    except Exception as e:
        logger.error(f"Failed to parse recipe {recipe_path}: {e}")
        return None


def create_recipe_command(metadata: RecipeMetadata) -> None:
    """Create a Typer command for a recipe using its metadata."""
    help_text = metadata.docstring or f"Run the {metadata.name} recipe"

    @recipe_app.command(name=metadata.name.replace('_', '-'), help=help_text)
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
                recipe_name=metadata.name,
                logging=logging,
                logging_level=logging_level,
                no_gui=no_gui,
                port=port,
                env=env,
                host=host,
                config=config_dict
            )
        except Exception as e:
            logger.error(f"Failed to run recipe {metadata.name}: {str(e)}")
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
    recipes_dir = Path(__file__).parent.parent / 'recipes'
    
    # Look for recipe modules
    for recipe_path in recipes_dir.glob('**/[!_]*.py'):
        if recipe_path.stem != 'runner':  # Skip the runner module
            if metadata := get_recipe_metadata(recipe_path):
                create_recipe_command(metadata)


__all__ = ['discover_recipes'] 
