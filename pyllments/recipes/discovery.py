"""Recipe discovery and metadata extraction.

Recipes in pyllments follow a specific structure to enable automatic discovery and configuration.
Each recipe should be a Python module that contains:

1. A module-level docstring describing the recipe's purpose
2. A Config dataclass defining the recipe's configuration parameters

Config Class Format
------------------
The Config class must be a dataclass with type-annotated fields. Each field can have metadata
that defines its behavior and constraints. For example:

    @dataclass
    class Config:
        '''Configuration for the recipe.'''
        field_name: int = field(
            default=100,
            metadata={
                "help": "Description of what this parameter does",
                "min": 0,        # Optional: Minimum value for numeric fields
                "max": 1000,     # Optional: Maximum value for numeric fields
            }
        )

Supported Metadata
----------------
- help: str
    Description of the parameter shown in CLI help and prompts
- min: number
    Minimum value for numeric parameters (int, float)
- max: number
    Maximum value for numeric parameters (int, float)

Example
-------
    @dataclass
    class Config:
        '''Configuration for a chat interface.'''
        width: int = field(
            default=800,
            metadata={
                "help": "Width of the chat interface in pixels",
                "min": 400,
                "max": 2000
            }
        )
        model_name: str = field(
            default="gpt-3.5-turbo",
            metadata={
                "help": "Name of the LLM model to use"
            }
        )
"""

import ast
from pathlib import Path
from typing import Dict, Optional

from pyllments.logging import logger


def extract_config_metadata(node: ast.ClassDef) -> Optional[Dict]:
    """
    Extract metadata from a Config class definition.

    This function parses the AST (abstract syntax tree) of a Config class to retrieve:
      - The class-level docstring.
      - A dictionary mapping each field name to a dictionary with field information,
        including its type, default value (if any), and metadata (such as help text and constraints).

    Parameters
    ----------
    node : ast.ClassDef
        The AST node representing the Config class.

    Returns
    -------
    Optional[Dict]
        A dictionary with keys:
          - 'docstring': The docstring of the class.
          - 'fields': A mapping from field names to field information (type, default, metadata).
        Returns None if no fields are found.
    """
    # Retrieve the class-level docstring.
    doc = ast.get_docstring(node)
    fields = {}

    # Iterate over each element in the class body.
    for item in node.body:
        # Process only annotated assignments with a proper field name.
        if isinstance(item, ast.AnnAssign) and hasattr(item.target, 'id'):
            field_name = item.target.id  # Name of the field.

            # Convert the annotation AST node to a string for type representation.
            field_type = ast.unparse(item.annotation) if item.annotation is not None else None
            field_data = {}
            if field_type:
                field_data['type'] = field_type

            default_value = None

            # Check if the field value is defined using a call to the 'field' function.
            if isinstance(item.value, ast.Call) and getattr(item.value.func, 'id', None) == 'field':
                # Iterate over keyword arguments to extract 'default' or 'default_factory' value.
                for kw in item.value.keywords:
                    if kw.arg == 'default':
                        try:
                            default_value = ast.literal_eval(kw.value)
                        except Exception as e:
                            logger.error(f"Failed to eval default for field {field_name}: {e}")
                    elif kw.arg == 'default_factory':
                        if isinstance(kw.value, ast.Name):
                            # Handle common default factories.
                            if kw.value.id == 'dict':
                                default_value = {}
                            elif kw.value.id == 'list':
                                default_value = []
                            else:
                                logger.warning(f"Unknown default_factory {kw.value.id} for field {field_name}, skipping evaluation.")
                        else:
                            try:
                                default_value = ast.literal_eval(kw.value)
                            except Exception as e:
                                logger.error(f"Failed to eval default_factory for field {field_name}: {e}")
                # Iterate again to extract 'metadata' if available.
                for kw in item.value.keywords:
                    if kw.arg == 'metadata' and isinstance(kw.value, ast.Dict):
                        # Build metadata by extracting allowed keys ('help', 'min', 'max').
                        metadata = {
                            k.value: v.value
                            for k, v in zip(kw.value.keys, kw.value.values)
                            if isinstance(k, ast.Str) and k.value in ('help', 'min', 'max')
                        }
                        if metadata:
                            field_data['metadata'] = metadata
            else:
                # For fields not using the 'field' function, attempt direct evaluation.
                try:
                    default_value = ast.literal_eval(item.value)
                except Exception:
                    pass
            if default_value is not None:
                field_data['default'] = default_value

            fields[field_name] = field_data

    # Return the gathered metadata if any fields were identified; otherwise, return None.
    return {'docstring': doc, 'fields': fields} if fields else None


def get_recipe_metadata(recipe_path: Path) -> Optional[Dict]:
    """
    Extract metadata from a recipe file without executing it.
    """
    try:
        with recipe_path.open('r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        metadata = {'docstring': ast.get_docstring(tree)}

        # Look for the Config class decorated with dataclass
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Config':
                if any(getattr(decorator, 'id', None) == 'dataclass' for decorator in node.decorator_list):
                    if config_meta := extract_config_metadata(node):
                        metadata['config'] = config_meta
                    break
        return metadata
    except Exception as e:
        logger.error(f"Failed to parse recipe {recipe_path}: {e}")
        return None


def discover_recipes() -> Dict[str, Dict]:
    """
    Discover all available recipes and return their metadata.
    """
    recipes = {}
    recipes_dir = Path(__file__).parent

    for recipe_path in recipes_dir.glob('**/[!_]*.py'):
        if recipe_path.stem not in ['discovery', 'runner']:
            if (metadata := get_recipe_metadata(recipe_path)):
                recipes[recipe_path.stem] = metadata
    return recipes