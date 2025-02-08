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
    recipes_dir = Path(__file__).parent
    
    # Try directory-based recipe first
    recipe_file = recipes_dir / recipe_name / f"{recipe_name}.py"
    if recipe_file.exists():
        return recipe_file
        
    # Try flat file structure
    recipe_file = recipes_dir / f"{recipe_name}.py"
    if recipe_file.exists():
        return recipe_file
        
    raise FileNotFoundError(f"Recipe {recipe_name} not found")


def run_recipe(
    recipe_name: str,
    logging: bool = False,
    logging_level: str = 'INFO',
    no_gui: bool = False,
    port: int = 8000,
    env: Optional[str] = None,
    host: str = "127.0.0.1",
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
        Network interface to bind the server to, by default "127.0.0.1"
    config : Optional[dict[str, Any]], optional
        Configuration parameters for the recipe, by default None
    """
    try:
        recipe_path = get_recipe_path(recipe_name)
        logger.info(f"Running recipe {recipe_name} from {recipe_path}")
        
        # Use the serve functionality from pyllments.serve
        serve(
            filename=str(recipe_path),
            inline=False,
            logging=logging,
            logging_level=logging_level,
            find_gui=not no_gui,
            port=port,
            env=env,
            host=host,
            config=config or {}
        )
    except Exception as e:
        logger.error(f"Failed to run recipe {recipe_name}: {str(e)}")
        raise 