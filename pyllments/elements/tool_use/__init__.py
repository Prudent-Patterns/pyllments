from .tool_use_element import ToolUseElement
from .tool_use_model import ToolUseModel, build_adapters
from .tool_adapter import ToolAdapter, ToolSpec, ToolResult, ToolError
from .function_tool_adapter import FunctionToolAdapter
from .tool_invocation_context import (
    AbortSignal,
    ToolCancelled,
    ToolInvocationContext,
)

__all__ = [
    "ToolUseElement",
    "ToolUseModel",
    "ToolAdapter",
    "ToolSpec",
    "ToolResult",
    "ToolError",
    "MCPToolAdapter",
    "FunctionToolAdapter",
    "AbortSignal",
    "ToolCancelled",
    "ToolInvocationContext",
    "build_adapters",
]


def __getattr__(name):
    # The MCP adapter imports the mcp client, which the Worker edition lacks.
    if name == "MCPToolAdapter":
        from .mcp_tool_adapter import MCPToolAdapter

        return MCPToolAdapter
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
