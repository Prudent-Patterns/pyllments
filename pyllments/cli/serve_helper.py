"""
This module centralizes common CLI options and their metadata.
"""

import json
from dataclasses import dataclass
from inspect import Parameter, Signature
from typing import Any, Dict, List, Optional, Callable
import typer
from typing import Annotated

from pyllments.common.type_utils import TypeMapper

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
        # Use positional default first so Option(default, *param_decls) signature is correct
        return typer.Option(self.default, help=self.help, show_default=True)

    def to_parameter(self) -> Parameter:
        """
        Returns an inspect.Parameter instance for dynamic signature building.
        """
        # Explicitly supply the CLI flag name for this common option
        flag = f"--{self.name.replace('_','-')}"
        # Build an Annotated type for this common option: flag name then help
        annotated_type = Annotated[
            self.type,
            typer.Option(
                flag,
                help=self.help,
                show_default=True
            )
        ]
        return Parameter(
            name=self.name,
            kind=Parameter.KEYWORD_ONLY,
            annotation=annotated_type,
            default=self.default if self.default is not ... else Parameter.empty,
        )

class FieldConfigProcessor:
    """
    Utility class for processing field configurations from dataclasses or dynamic sources.
    
    Consolidates the logic for extracting field metadata, types, and defaults.
    """
    
    @staticmethod
    def create_typer_parameter(field_name: str, field_data: Dict[str, Any]) -> Parameter:
        """
        Create a Typer Parameter from field configuration data.
        
        Parameters
        ----------
        field_name : str
            Name of the field
        field_data : Dict[str, Any]
            Field configuration containing type, default, metadata etc.
            
        Returns
        -------
        Parameter
            Configured Parameter for dynamic signature building
        """
        param_name = field_name.replace("-", "_")
        base_type = field_data.get("type") or str
        base_type = TypeMapper.string_to_type(base_type)

        default_value = field_data.get("default", None)
        param_default = default_value if default_value is not ... else Parameter.empty

        help_text = field_data.get("metadata", {}).get("help", "")
        annotated_type = Annotated[
            base_type,
            typer.Option(f"--{param_name}", help=help_text, show_default=True)
        ]

        return Parameter(
            name=param_name,
            kind=Parameter.KEYWORD_ONLY,
            annotation=annotated_type,
            default=param_default,
        )

    @staticmethod
    def process_config_fields(fields: Dict[str, Dict[str, Any]]) -> List[Parameter]:
        """
        Process a dictionary of field configurations into Typer Parameters.
        
        Parameters
        ----------
        fields : Dict[str, Dict[str, Any]]
            Dictionary mapping field names to their configuration
            
        Returns
        -------
        List[Parameter]
            List of configured Parameters ready for signature building
        """
        dynamic_params = []
        for field_name, field_data in fields.items():
            if not field_name:
                continue
            param = FieldConfigProcessor.create_typer_parameter(field_name, field_data)
            dynamic_params.append(param)
        return dynamic_params

class CommonOptions:
    """
    Centralizes the common CLI options and provides utilities for consistent argument handling.
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
            "host": CommonOption(
                name="host",
                type=str,
                default="0.0.0.0",
                help="Network interface to bind the server to. '0.0.0.0' means all interfaces, '127.0.0.1' for localhost only."
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

    def extract_common_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract common CLI arguments from kwargs dict.
        
        Parameters
        ----------
        kwargs : Dict[str, Any]
            Dictionary containing CLI arguments
            
        Returns
        -------
        Dict[str, Any]
            Dictionary containing only the common CLI arguments
        """
        common_args = {
            name: kwargs.get(name)
            for name in self.options.keys()
            if name in kwargs
        }
        
        return self._apply_smart_defaults(common_args)

    def _apply_smart_defaults(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply smart defaults like auto-enabling logging when logging_level is non-default.
        
        Parameters
        ----------
        args : Dict[str, Any]
            Dictionary containing CLI arguments
            
        Returns
        -------
        Dict[str, Any]
            Updated dictionary with smart defaults applied
        """
        # Auto-enable logging if non-default logging level is specified
        if (args.get("logging_level") not in [None, self.options["logging_level"].default] 
            and not args.get("logging")):
            args["logging"] = True
            
        return args

    def to_serve_kwargs(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert CLI arguments to serve function parameters.
        
        This handles parameter name mapping and value transformations:
        - no_gui -> find_gui (inverted)
        - filters out profile (not a serve parameter)
        
        Parameters
        ----------
        cli_args : Dict[str, Any]
            Dictionary containing CLI arguments
            
        Returns
        -------
        Dict[str, Any]
            Dictionary with parameters suitable for the serve function
        """
        serve_args = {}
        
        # Direct mappings (same name, same value)
        direct_mappings = ["logging", "logging_level", "env", "host", "port"]
        for arg in direct_mappings:
            if arg in cli_args and cli_args[arg] is not None:
                serve_args[arg] = cli_args[arg]
        
        # Inverted mapping: no_gui -> find_gui
        if "no_gui" in cli_args:
            serve_args["find_gui"] = not cli_args["no_gui"]
        
        # profile is handled separately by CLI commands, not passed to serve
        
        return serve_args

    def parse_json_config(self, config_str: str) -> Dict[str, Any]:
        """
        Parse JSON configuration string with proper error handling.
        
        Parameters
        ----------
        config_str : str
            JSON string to parse
            
        Returns
        -------
        Dict[str, Any]
            Parsed configuration dictionary
            
        Raises
        ------
        typer.BadParameter
            If JSON is invalid or not a dictionary
        """
        try:
            config_dict = json.loads(config_str)
            if not isinstance(config_dict, dict):
                raise ValueError("config JSON must be a dict")
            return config_dict
        except Exception as e:
            raise typer.BadParameter(f"Invalid --config JSON: {e}")

    def build_serve_kwargs(self, cli_args: Dict[str, Any], **additional_kwargs) -> Dict[str, Any]:
        """
        Build complete serve function kwargs from CLI arguments and additional parameters.
        
        Parameters
        ----------
        cli_args : Dict[str, Any]
            CLI arguments dictionary
        **additional_kwargs
            Additional parameters to add to serve kwargs
            
        Returns
        -------
        Dict[str, Any]
            Complete serve function kwargs
        """
        serve_kwargs = self.to_serve_kwargs(cli_args)
        serve_kwargs.update(additional_kwargs)
        return serve_kwargs

    def execute_with_profiling(self, cli_args: Dict[str, Any], func: Callable, *args, **kwargs):
        """
        Execute a function with optional profiling based on CLI arguments.
        
        This consolidates the common pattern of:
        1. Extract profile flag from CLI args
        2. Create wrapper function
        3. Call handle_profiling
        
        Note: Only the 'profile' flag is extracted from cli_args. All other
        arguments should be passed via *args and **kwargs to avoid conflicts
        with function signatures that don't accept all CLI arguments.
        
        Parameters
        ----------
        cli_args : Dict[str, Any]
            CLI arguments containing profile flag
        func : Callable
            Function to execute
        *args, **kwargs
            Arguments to pass to the function
        """
        profile = cli_args.get("profile", False)
        
        def wrapper():
            return func(*args, **kwargs)
        
        return self.handle_profiling(profile, wrapper)

    def handle_profiling(self, profile: bool, func_to_profile, *args, **kwargs):
        """
        Handle profiling logic consistently across commands.
        
        Parameters
        ----------
        profile : bool
            Whether to enable profiling
        func_to_profile : callable
            Function to profile
        *args, **kwargs
            Arguments to pass to the function
            
        Returns
        -------
        Any
            Return value of the profiled function
        """
        if profile:
            import cProfile
            import pstats
            from io import StringIO
            
            pr = cProfile.Profile()
            pr.enable()
            
            try:
                result = func_to_profile(*args, **kwargs)
                return result
            finally:
                pr.disable()
                s = StringIO()
                ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
                ps.print_stats(30)
                print(s.getvalue())
        else:
            return func_to_profile(*args, **kwargs)

    def build_cli_args_dict(self, **kwargs) -> Dict[str, Any]:
        """
        Build CLI arguments dictionary from individual parameters.
        
        This eliminates the need to manually construct the CLI args dict
        in multiple places with the same parameter names.
        
        Parameters
        ----------
        **kwargs
            Individual CLI argument values
            
        Returns
        -------
        Dict[str, Any]
            CLI arguments dictionary with only known common options
        """
        cli_args = {
            name: kwargs.get(name)
            for name in self.options.keys()
            if name in kwargs
        }
        
        return self._apply_smart_defaults(cli_args)

class CommandRegistrar:
    """
    Utility class for registering dynamic commands with common + field-specific arguments.
    
    Consolidates the pattern used in recipe commands and potentially other dynamic CLI commands.
    """
    
    @staticmethod
    def register_dynamic_command(
        app: typer.Typer,
        command_name: str,
        metadata: Dict[str, Any],
        command_func: Callable,
        common_options: CommonOptions,
        context_settings: Optional[Dict[str, Any]] = None
    ):
        """
        Register a dynamic command with common CLI options plus field-specific options.
        
        Parameters
        ----------
        app : typer.Typer
            The Typer app to register the command with
        command_name : str
            Name of the command
        metadata : Dict[str, Any]
            Command metadata containing config fields and docstring
        command_func : Callable
            Function to execute when command is called
        common_options : CommonOptions
            CommonOptions instance for shared CLI arguments
        context_settings : Optional[Dict[str, Any]], optional
            Context settings for the command, by default None
        """
        config = metadata.get("config", {}) or {}
        fields = config.get("fields", {})

        # Common parameters (logging, port, etc.)
        common_params = common_options.get_parameters()

        # Use consolidated field processing utilities
        dynamic_params = FieldConfigProcessor.process_config_fields(fields)

        all_params = common_params + dynamic_params
        new_signature = Signature(parameters=all_params)

        def command_wrapper(**kwargs):
            # Extract metadata needed by the command function
            command_args = {
                'command_name': command_name,
                'metadata': metadata,
                'fields': fields,
                'kwargs': kwargs,
                'common_options': common_options
            }
            return command_func(**command_args)

        command_wrapper.__signature__ = new_signature
        
        # Build docstring from metadata
        doc = metadata.get("docstring", "")
        if config_doc := config.get("docstring"):
            doc += f"\n\nConfiguration:\n{config_doc}"
        command_wrapper.__doc__ = doc

        # Default context settings if none provided
        if context_settings is None:
            context_settings = {"allow_extra_args": True, "ignore_unknown_options": False}

        app.command(
            name=command_name,
            context_settings=context_settings,
        )(command_wrapper)