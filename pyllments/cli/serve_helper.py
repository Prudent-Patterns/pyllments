"""
This module centralizes common CLI options and their metadata.
"""

from dataclasses import dataclass
from inspect import Parameter
from typing import Any, Dict, List, Optional
import typer

@dataclass
class CommonOption:
    """
    Stores metadata for a common CLI option.
    """
    name: str
    type: type
    default: Any
    help: str

    def to_typer_option(self) -> Any:
        """
        Returns a Typer Option with the appropriate default and help text.
        """
        return typer.Option(self.default, help=self.help)

    def to_parameter(self) -> Parameter:
        """
        Returns an inspect.Parameter instance for dynamic signature building.
        """
        return Parameter(
            name=self.name,
            kind=Parameter.KEYWORD_ONLY,
            annotation=self.type,
            default=self.default if self.default is not ... else Parameter.empty,
        )

class CommonOptions:
    """
    Centralizes the common CLI options.
    """
    def __init__(self):
        self.options: Dict[str, CommonOption] = {
            "logging": CommonOption(
                name="logging",
                type=bool,
                default=False,
                help="Enable logging."
            ),
            "logging_level": CommonOption(
                name="logging_level",
                type=str,
                default="INFO",
                help="Set logging level."
            ),
            "no_gui": CommonOption(
                name="no_gui",
                type=bool,
                default=False,
                help="Do not initialize GUI components."
            ),
            "port": CommonOption(
                name="port",
                type=int,
                default=8000,
                help="Port on which to run the server."
            ),
            "env": CommonOption(
                name="env",
                type=Optional[str],
                default=None,
                help="Path to the .env file containing environment variables."
            ),
            "profile": CommonOption(
                name="profile",
                type=bool,
                default=False,
                help="Enable profiling of the application."
            ),
        }

    def get_typer_options(self) -> Dict[str, Any]:
        """
        Returns a mapping of option names to Typer options
        for use in static command definitions.
        """
        return {name: arg.to_typer_option() for name, arg in self.options.items()}

    def get_parameters(self) -> List[Parameter]:
        """
        Returns a list of inspect.Parameters for dynamically constructing a function signature.
        """
        return [arg.to_parameter() for arg in self.options.values()]