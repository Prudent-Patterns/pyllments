"""
Core functionality for running pyllments recipes.
"""
import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Type
from dataclasses import dataclass

from pyllments.logging import logger
from pyllments.serve import serve
from pyllments.cli.serve_helper import CommonOptions


def load_recipe_module(recipe_path: Path):
    """Load a recipe module from a path.
    
    Parameters
    ----------
    recipe_path : Path
        Path to the recipe module
        
    Returns
    -------
    module
        The loaded recipe module
    """
    spec = importlib.util.spec_from_file_location(
        f"pyllments.recipes.{recipe_path.stem}",
        recipe_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_recipe_path(recipe_name: str) -> Path:
    """Get the path to a recipe file.
    
    Parameters
    ----------
    recipe_name : str
        Name of the recipe to locate
        
    Returns
    -------
    Path
        Path to the recipe file
        
    Raises
    ------
    FileNotFoundError
        If the recipe cannot be found
    """
    # Base directory for recipes helper modules
    recipes_base_dir = Path(__file__).parent
    # Subdirectory where actual recipe implementations are stored
    available_recipes_dir = recipes_base_dir / 'available_recipes'
    
    # Try directory-based recipe structure within available_recipes first
    recipe_file = available_recipes_dir / recipe_name / f"{recipe_name}.py"
    if recipe_file.exists():
        return recipe_file
        
    # Try flat file structure within available_recipes
    recipe_file = available_recipes_dir / f"{recipe_name}.py"
    if recipe_file.exists():
        return recipe_file
        
    raise FileNotFoundError(f"Recipe {recipe_name} not found in {available_recipes_dir}")


def run_recipe(
    recipe_name: str,
    logging: bool = False,
    logging_level: str = 'INFO',
    no_gui: bool = False,
    port: int = 8000,
    env: Optional[str] = None,
    host: str = "0.0.0.0",
    config: Optional[dict[str, Any]] = None
) -> None:
    """Run a recipe.
    
    Parameters
    ----------
    recipe_name : str
        Name of the recipe to run
    logging : bool, optional
        Enable logging, by default False
    logging_level : str, optional
        Set logging level, by default 'INFO'
    no_gui : bool, optional
        Don't look for GUI components, by default False
    port : int, optional
        Port to run server on, by default 8000
    env : Optional[str], optional
        Path to .env file, by default None
    host : str, optional
        Network interface to bind the server to, by default "0.0.0.0"
    config : Optional[dict[str, Any]], optional
        Configuration parameters for the recipe, by default None
    """
    try:
        recipe_path = get_recipe_path(recipe_name)
        logger.info(f"Running recipe {recipe_name} from {recipe_path}")
        
        # Use CommonOptions for consistent parameter conversion
        common_options = CommonOptions()
        cli_args = common_options.build_cli_args_dict(
            logging=logging,
            logging_level=logging_level,
            no_gui=no_gui,
            port=port,
            env=env,
            host=host
        )
        
        # Build serve kwargs using consolidated utility
        serve_kwargs = common_options.build_serve_kwargs(
            cli_args,
            filename=str(recipe_path),
            inline=False,
            config=config or {}
        )
        
        # Use the serve functionality from pyllments.serve
        serve(**serve_kwargs)
    except Exception as e:
        logger.error(f"Failed to run recipe {recipe_name}: {str(e)}")
        raise 