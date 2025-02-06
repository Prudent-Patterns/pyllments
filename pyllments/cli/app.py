"""Core CLI application and commands."""
import cProfile
import pstats
from io import StringIO
from typing import Optional, Dict, Any, List, Annotated
import typer
from rich.console import Console
from rich.table import Table
from inspect import Parameter, Signature
from typing_extensions import Annotated

from pyllments.serve import serve as serve_file
from pyllments.logging import logger
from pyllments.recipes import discover_recipes, run_recipe


app = typer.Typer(no_args_is_help=True)

@app.command('serve')
def serve(
    filename: str, 
    logging: bool = typer.Option(False, help="Enable logging."),
    logging_level: str = typer.Option("INFO", help="Set logging level."),
    no_gui: bool = typer.Option(False, help="Don't look for GUI components."),
    port: int = typer.Option(8000, help="Port to run server on."),
    env: Optional[str] = typer.Option(None, help="Path to .env file."),
    host: str = typer.Option(
        '127.0.0.1', 
        "--host", 
        "-H", 
        help="Network interface to bind the server to. Defaults to localhost (127.0.0.1) for safer local development."
    ),
    profile: bool = typer.Option(False, help="Enable profiling output."),
    config: List[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="Additional configuration options for the served file. Provide either multiple key=value pairs or a single dictionary literal (e.g. '{\"key\": \"value\"}').",
        show_default=False
    )
):
    """Start a Pyllments server"""
    logger.info(f"Starting Pyllments server for {filename}...")
    
    config_dict: Dict[str, Any] = {}
    if config:
        # Check if a single argument is provided and it is a dict literal.
        if len(config) == 1 and config[0].strip().startswith("{") and config[0].strip().endswith("}"):
            import ast
            try:
                parsed = ast.literal_eval(config[0])
                if not isinstance(parsed, dict):
                    raise ValueError("Provided config is not a dictionary")
                config_dict = parsed
            except Exception as e:
                raise typer.BadParameter(f"Invalid config dictionary: {e}")
        else:
            for item in config:
                if "=" in item:
                    key, value = item.split("=", 1)
                    config_dict[key] = value
                else:
                    raise typer.BadParameter(f"Invalid config option format: {item}. Expected key=value.")
    
    if profile:
        pr = cProfile.Profile()
        pr.enable()
        
    try:
        serve_file(
            filename=filename,
            inline=False,
            logging=logging,
            logging_level=logging_level,
            find_gui=not no_gui,
            port=port,
            env=env,
            config=config_dict,
            host=host
        )
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
      - fixed/common options (logging, logging_level, no_gui, port, env, host, profile)
      - additional options extracted from metadata['config']['fields'].
    """
    # Retrieve dynamic configuration info from metadata.
    config = metadata.get("config", {})
    fields = config.get("fields", {})

    # Build a list of common parameters with the host option added.
    common_params = [
       Parameter(
           'logging',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[bool, typer.Option(help="Enable logging.", show_default=True)],
           default=False
       ),
       Parameter(
           'logging_level',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[str, typer.Option(help="Set logging level.", show_default=True)],
           default="INFO"
       ),
       Parameter(
           'no_gui',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[bool, typer.Option(help="Don't look for GUI components.", show_default=True)],
           default=False
       ),
       Parameter(
           'port',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[int, typer.Option(help="Port to run server on.", show_default=True)],
           default=8000
       ),
       Parameter(
           'env',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[Optional[str], typer.Option(help="Path to .env file.", show_default=True)],
           default=None
       ),
       Parameter(
           'host',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[str, typer.Option(
               "--host",
               "-H",
               help="Network interface to bind the server to. Defaults to localhost (127.0.0.1) for safer local development.",
               show_default=True
           )],
           default="127.0.0.1"
       ),
       Parameter(
           'profile',
           kind=Parameter.KEYWORD_ONLY,
           annotation=Annotated[bool, typer.Option(help="Enable profiling output.", show_default=True)],
           default=False
       ),
    ]

    # Build dynamic parameters based on the recipe's configuration fields.
    dynamic_params = []
    for field_name, field_data in fields.items():
        # Ensure the field name is non-empty and normalize it to a valid Python identifier.
        if not field_name:
            continue
        param_name = field_name.replace("-", "_")
        
        # Retrieve the base type from metadata.
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
            param_default = Parameter.empty
        else:
            param_default = default_value
        
        # Retrieve the help text for this field.
        help_text = field_data.get("metadata", {}).get("help", "")
        
        # Build an Annotated type for this option.
        annotated_type = Annotated[
            base_type,
            typer.Option(f"--{param_name}", help=help_text, show_default=True)
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
        host_val = kwargs.get("host")  # Extract host option.
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
                host=host_val,  # Passing the host option.
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
    command_impl = run_app.command(
        name=recipe_name,
        context_settings={"allow_extra_args": True, "ignore_unknown_options": False},
    )(command_impl)

    return command_impl

# Add recipe commands dynamically
recipes = discover_recipes()
for recipe_name, metadata in recipes.items():
    register_recipe_command(recipe_name, metadata) 