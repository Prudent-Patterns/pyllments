"""Serve command for Pyllments CLI."""
from typing import Optional
import typer

from pyllments.serve import serve as serve_file
from pyllments.logging import logger
from pyllments.cli.serve_helper import CommonOptions

app = typer.Typer(
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": True}
)

# Get shared options for serve command
common_opts = CommonOptions().get_typer_options()

@app.callback()
def serve(
    filename: str,
    logging: bool = common_opts["logging"],
    logging_level: str = common_opts["logging_level"],
    no_gui: bool = common_opts["no_gui"],
    port: int = common_opts["port"],
    env: Optional[str] = common_opts["env"],
    host: str = common_opts["host"],
    profile: bool = common_opts["profile"],
    config: str = typer.Option(
        "{}", "--config", "-c",
        help="Additional configuration options for the served file as JSON (string)",
        show_default=False
    )
):
    """Start a Pyllments server"""
    logger.info(f"Starting Pyllments server for {filename}...")

    common_options = CommonOptions()
    
    # Parse JSON config using consolidated utility
    config_dict = common_options.parse_json_config(config)

    # Build CLI args using consolidated utility
    cli_args = common_options.build_cli_args_dict(
        logging=logging,
        logging_level=logging_level,
        no_gui=no_gui,
        port=port,
        env=env,
        host=host,
        profile=profile
    )
    
    serve_kwargs = common_options.build_serve_kwargs(
        cli_args,
        filename=filename,
        inline=False,
        config=config_dict
    )

    # Execute with profiling using consolidated utility
    common_options.execute_with_profiling(cli_args, serve_file, **serve_kwargs) 