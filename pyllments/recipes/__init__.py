"""
Recipe management for pyllments.

This module provides functionality to discover and run pre-built pyllments recipes.
"""
from .discovery import discover_recipes, get_recipe_metadata
from .runner import run_recipe

__all__ = ['discover_recipes', 'get_recipe_metadata', 'run_recipe'] 