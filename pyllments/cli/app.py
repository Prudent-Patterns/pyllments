"""Core CLI application and commands."""
import cProfile
import pstats
from io import StringIO
from typing import Optional, Dict, Any, Annotated
import typer
from rich.console import Console
from rich.table import Table
import click  # Directly import Click to construct options
import inspect
from inspect import Parameter, Signature
from typing_extensions import Annotated

from pyllments.serve import serve as serve_file
from pyllments.logging import logger
from pyllments.recipes import discover_recipes, get_recipe_metadata, run_recipe


app = typer.Typer(no_args_is_help=True)


@app.command('serve')
def serve(
    filename: str, 
    logging: bool = False, 
    logging_level: str = 'INFO', 
    no_gui: bool = False, 
    port: int = 8000, 
    env: str = None,
    profile: bool = False
):
    """Start a Pyllments server.
    
    Args:
        filename: Path to the Python file containing the flow
        logging: Enable logging
        logging_level: Set logging level
        no_gui: Don't look for GUI components
        port: Port to run server on
        env: Path to .env file
        profile: Enable profiling output
    """
    logger.info(f"Starting Pyllments server for {filename}...")
    
    if profile:
        pr = cProfile.Profile()
        pr.enable()
        
    try:
        serve_file(filename=filename, inline=False, logging=logging, logging_level=logging_level, find_gui=not no_gui, port=port, env=env)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise  # Re-raise to show full traceback
    finally:
        if profile:
            pr.disable()
            s = StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)  # Print top 30 time-consuming functions
            print(s.getvalue())


# Create recipe subcommand group
recipe_app = typer.Typer(help="Manage and run Pyllments recipes")
app.add_typer(recipe_app, name="recipe")


@recipe_app.command('list')
def list_recipes():
    """List all available recipes."""
    recipes = discover_recipes()
    
    if not recipes:
        typer.echo("No recipes found.")
        raise typer.Exit()
    
    # Create a rich table for better formatting
    table = Table(title="Available Recipes")
    table.add_column("Recipe", style="cyan")
    table.add_column("Description")
    table.add_column("Configuration Arguments", style="green")
    
    for name, metadata in recipes.items():
        # Get first line of docstring for description
        description = metadata.get('docstring', '').split('\n')[0]
        
        # Get config argument names if any
        config_args = []
        if config := metadata.get('config'):
            config_args = list(config.get('fields', {}).keys())
        
        # Format config args nicely
        config_str = ', '.join(config_args) if config_args else 'None'
        
        table.add_row(name, description, config_str)
    
    console = Console()
    console.print(table)
    console.print("\nUse 'pyllments recipe run <recipe-name> --help' to see configuration options", style="dim")


# Create run subcommand group
run_app = typer.Typer(help="Run a Pyllments recipe")
recipe_app.add_typer(run_app, name="run")


def register_recipe_command(recipe_name: str, metadata: dict):
    """
    Dynamically register a command for the given recipe.
    
    This version builds a dynamic function signature based on:
      - fixed/common options (logging, logging_level, no_gui, port, env, profile)
      - additional options extracted from metadata['config']['fields'].
    
    The resulting signature is assigned to the command callback so that
    both `--help` and option parsing work as expected.
    """
    # Retrieve dynamic configuration info from metadata.
    config = metadata.get("config", {})
    fields = config.get("fields", {})

    # Build a list of common parameters (as Keyword-Only parameters).
    common_params = [
       Parameter('logging', kind=Parameter.KEYWORD_ONLY, annotation=bool, default=False),
       Parameter('logging_level', kind=Parameter.KEYWORD_ONLY, annotation=str, default="INFO"),
       Parameter('no_gui', kind=Parameter.KEYWORD_ONLY, annotation=bool, default=False),
       Parameter('port', kind=Parameter.KEYWORD_ONLY, annotation=int, default=8000),
       Parameter('env', kind=Parameter.KEYWORD_ONLY, annotation=Optional[str], default=None),
       Parameter('profile', kind=Parameter.KEYWORD_ONLY, annotation=bool, default=False),
    ]

    # Build dynamic parameters based on the recipe's configuration fields.
    dynamic_params = []
    for field_name, field_data in fields.items():
        # Ensure the field name is non-empty and normalize it to a valid Python identifier.
        if not field_name:
            continue
        param_name = field_name.replace("-", "_")
        
        # Get the base type from metadata.
        base_type = field_data.get("type")
        if base_type is None:
            base_type = str
        elif isinstance(base_type, str):
            # A simple mapping for common types; expand as needed.
            type_mappings = {
                "int": int,
                "float": float,
                "bool": bool,
                "str": str,
            }
            base_type = type_mappings.get(base_type.lower(), str)
        
        # Get the default value. If the default is Ellipsis, mark it as required.
        default_value = field_data.get("default", None)
        if default_value is ...:
            option_default = ...   # indicates required; the Parameter.default will be Parameter.empty
            param_default = Parameter.empty
        else:
            option_default = default_value
            param_default = default_value
        
        # Get the help text from the field metadata, if any.
        help_text = field_data.get("metadata", {}).get("help", "")
        
        # Build an Annotated type for this option.
        # Note: We no longer pass a default here, so only the Parameter default is used.
        annotated_type = Annotated[
            base_type,
            typer.Option(*[f"--{param_name}"], help=help_text, show_default=True)
        ]
        
        dynamic_params.append(
            Parameter(
                name=param_name,
                kind=Parameter.KEYWORD_ONLY,
                annotation=annotated_type,
                default=param_default,
            )
        )

    # Combine both common and dynamic parameters.
    all_params = common_params + dynamic_params
    new_signature = Signature(parameters=all_params)

    # Define the command callback that uses **kwargs.
    # Typer will inject the options based on the (fake) signature we assign.
    def command_impl(**kwargs):
        """
        Run the recipe.
        """
        # Extract common options.
        logging_val = kwargs.get("logging")
        logging_level_val = kwargs.get("logging_level")
        no_gui_val = kwargs.get("no_gui")
        port_val = kwargs.get("port")
        env_val = kwargs.get("env")
        profile_val = kwargs.get("profile")
        
        # Build recipe-specific configuration from dynamic parameters.
        recipe_config = {}
        for field_name in fields.keys():
            if field_name in kwargs:
                recipe_config[field_name] = kwargs[field_name]

        if profile_val:
            import cProfile
            pr = cProfile.Profile()
            pr.enable()
        try:
            run_recipe(
                recipe_name=recipe_name,
                logging=logging_val,
                logging_level=logging_level_val,
                no_gui=no_gui_val,
                port=port_val,
                env=env_val,
                config=recipe_config,
            )
        except Exception as e:
            logger.error(f"Failed to run recipe {recipe_name}: {str(e)}")
            raise
        finally:
            if profile_val:
                pr.disable()
                from io import StringIO
                import pstats
                s = StringIO()
                ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
                ps.print_stats(30)
                print(s.getvalue())

    # Assign our new signature to the command callback. This is a documented use of __signature__.
    command_impl.__signature__ = new_signature

    # Set the command's docstring.
    doc = metadata.get("docstring", "")
    config_doc = config.get("docstring")
    if config_doc:
         doc += f"\n\nConfiguration:\n{config_doc}"
    command_impl.__doc__ = doc

    # Finally, register the command callback with Typer.
    # We use the public 'command' decorator on our 'run_app' Typer instance.
    command_impl = run_app.command(
        name=recipe_name,
        # Pass context_settings if needed.
        context_settings={"allow_extra_args": True, "ignore_unknown_options": False},
    )(command_impl)

    return command_impl


# Add recipe commands dynamically
recipes = discover_recipes()
for recipe_name, metadata in recipes.items():
    register_recipe_command(recipe_name, metadata) 