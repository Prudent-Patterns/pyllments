from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Callable

from pyllments.runtime.loop_registry import LoopRegistry

from .signature_schema import parameters_schema, validate_arguments
from .tool_adapter import ToolResult, ToolSpec
from .tool_invocation_context import ToolCancelled

if TYPE_CHECKING:
    from .tool_invocation_context import ToolInvocationContext


def result_text(result: Any) -> str:
    """What the model reads: strings as they are, data as JSON, the rest as str."""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list, tuple, int, float, bool)):
        return json.dumps(result, default=str)
    return str(result)


class FunctionToolAdapter:
    """
    Local Python function tool adapter with schema extraction and validation.

    Parameters
    ----------
    name : str
        The adapter's name, and the prefix of each tool's model-facing name
        when ``prefix_names`` is True.
    functions : list or dict
        The tools, by their own name or by the key given.
    tools_requiring_permission : list of str
        Function names the gateway must ask about before running.
    prefix_names : bool
        ``True`` exposes ``add`` as ``functions_add``, which keeps several
        adapters apart. ``False`` exposes it as ``add``, for a flow whose tool
        names are a contract of their own.
    """

    name = "functions"

    def __init__(
        self,
        *,
        name: str = "functions",
        functions: list[Callable] | dict[str, Callable] | None = None,
        tools_requiring_permission: list[str] | None = None,
        prefix_names: bool = True,
    ):
        self.name = name
        self.prefix_names = prefix_names
        self._functions: dict[str, Callable] = {}
        if isinstance(functions, dict):
            self._functions = dict(functions)
        elif functions:
            for func in functions:
                self._functions[func.__name__] = func
        self._tools_requiring_permission = set(tools_requiring_permission or [])
        self._schemas: dict[str, dict[str, Any]] = {}
        self._accepts_context: dict[str, bool] = {}
        self._tools: dict[str, ToolSpec] = {}
        self._setup_complete = False
        self.loop = LoopRegistry.get_loop()

    def model_tool_name(self, function_name: str) -> str:
        return f"{self.name}_{function_name}" if self.prefix_names else function_name

    async def setup(self) -> None:
        self._tools.clear()
        for fname, func in self._functions.items():
            schema, accepts_context = parameters_schema(func)
            self._schemas[fname] = schema
            self._accepts_context[fname] = accepts_context
            model_tool_name = self.model_tool_name(fname)
            self._tools[model_tool_name] = ToolSpec(
                adapter_name=self.name,
                provider_name=None,
                tool_name=fname,
                model_tool_name=model_tool_name,
                description=(func.__doc__ or "").strip(),
                parameters_schema=schema,
                permission_required=fname in self._tools_requiring_permission,
            )
        self._setup_complete = True

    async def await_ready(self):
        if not self._setup_complete:
            await self.setup()
        return self

    async def list_tools(self) -> dict[str, ToolSpec]:
        await self.await_ready()
        return dict(self._tools)

    async def call_tool(
        self,
        *,
        provider_name: str | None,
        tool_name: str,
        parameters: dict | None,
        context: ToolInvocationContext | None = None,
    ) -> ToolResult:
        await self.await_ready()
        func = self._functions.get(tool_name)
        if func is None:
            raise KeyError(f"Unknown function tool: {tool_name}")
        kwargs = validate_arguments(self._schemas[tool_name], parameters)
        if self._accepts_context.get(tool_name) and context is not None:
            kwargs["context"] = context
        try:
            # Sync tools run inline on the event loop; keep them lightweight/non-blocking.
            result = await func(**kwargs) if asyncio.iscoroutinefunction(func) else func(**kwargs)
        except ToolCancelled:
            raise
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        return ToolResult(
            content=[{"type": "text", "text": result_text(result)}],
            raw={"value": result},
        )

    async def close(self) -> None:
        return None
