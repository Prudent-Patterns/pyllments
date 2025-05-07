"""Recipe commands for Pyllments CLI."""
import typer
from rich.console import Console
from rich.table import Table
from inspect import Parameter, Signature
from typing import Optional, Any, List, Annotated

from pyllments.recipes import discover_recipes, run_recipe
from pyllments.logging import logger
from pyllments.cli.serve_helper import CommonOptions

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
        description = metadata.get("docstring", "").split("\n")[0]
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

def register_recipe_command(recipe_name: str, metadata: dict):
    """
    Dynamically register a command for the given recipe.
    """
    config = metadata.get("config", {}) or {}
    fields = config.get("fields", {})

    # Common parameters (logging, port, etc.)
    common_params = CommonOptions().get_parameters()

    # Dynamic parameters based on config fields
    dynamic_params = []
    for field_name, field_data in fields.items():
        if not field_name:
            continue
        param_name = field_name.replace("-", "_")
        base_type = field_data.get("type") or str
        if isinstance(base_type, str):
            type_mappings = {"int": int, "float": float, "bool": bool, "str": str}
            base_type = type_mappings.get(base_type.lower(), str)

        default_value = field_data.get("default", None)
        param_default = default_value if default_value is not ... else Parameter.empty

        help_text = field_data.get("metadata", {}).get("help", "")
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

    all_params = common_params + dynamic_params
    new_signature = Signature(parameters=all_params)

    def command_impl(**kwargs):
        logging_val = kwargs.get("logging")
        logging_level_val = kwargs.get("logging_level")
        no_gui_val = kwargs.get("no_gui")
        port_val = kwargs.get("port")
        env_val = kwargs.get("env")
        host_val = kwargs.get("host")
        profile_val = kwargs.get("profile")

        recipe_config = {
            field_name: kwargs.get(field_name)
            for field_name in fields.keys()
            if field_name in kwargs
        }

        if profile_val:
            import cProfile, pstats
            from io import StringIO as _StringIO
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
                host=host_val,
                config=recipe_config,
            )
        finally:
            if profile_val:
                pr.disable()
                s = _StringIO()
                ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
                ps.print_stats(30)
                print(s.getvalue())

    command_impl.__signature__ = new_signature
    doc = metadata.get("docstring", "")
    if config_doc := config.get("docstring"):
        doc += f"\n\nConfiguration:\n{config_doc}"
    command_impl.__doc__ = doc

    run_app.command(
        name=recipe_name,
        context_settings={"allow_extra_args": True, "ignore_unknown_options": False},
    )(command_impl)

# Register commands dynamically
for recipe_name, metadata in discover_recipes().items():
    register_recipe_command(recipe_name, metadata) 