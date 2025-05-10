"""Serve command for Pyllments CLI."""
import cProfile
import pstats
from io import StringIO
import json
from typing import Optional, List, Annotated
import typer

from pyllments.serve import serve as serve_file
from pyllments.logging import logger
from pyllments.cli.serve_helper import CommonOptions

app = typer.Typer(
    invoke_without_command=True,
    context_settings={"allow_interspersed_args": True}
)

# Shared options for serve command
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

    # Parse JSON string into a dict
    try:
        config_dict = json.loads(config)
        if not isinstance(config_dict, dict):
            raise ValueError("config JSON must be a dict")
    except Exception as e:
        raise typer.BadParameter(f"Invalid --config JSON: {e}")

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
    finally:
        if profile:
            pr.disable()
            s = StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)
            print(s.getvalue()) 