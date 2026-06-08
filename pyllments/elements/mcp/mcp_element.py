from pyllments.elements.tool_use import ToolUseElement


class MCPElement(ToolUseElement):
    """
    MCP-focused ToolUseElement convenience wrapper.

    Accepts ``mcps=`` and optional ``functions=`` and delegates to ToolUseElement adapters.
    """

    def __init__(self, *, mcps=None, functions=None, tools_requiring_permission=None, **params):
        super().__init__(
            mcps=mcps,
            functions=functions,
            tools_requiring_permission=tools_requiring_permission,
            **params,
        )
