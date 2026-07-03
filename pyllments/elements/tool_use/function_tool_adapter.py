from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, create_model

from pyllments.runtime.loop_registry import LoopRegistry

from .tool_adapter import ToolResult, ToolSpec
from .tool_invocation_context import ToolCancelled

if TYPE_CHECKING:
    from .tool_invocation_context import ToolInvocationContext

CONTEXT_PARAM_NAMES = frozenset({"context", "invocation_context"})


def _is_context_param(name: str, annotation: Any) -> bool:
    if name in CONTEXT_PARAM_NAMES:
        return True
    if annotation is inspect._empty:
        return False
    if isinstance(annotation, str):
        return annotation.endswith("ToolInvocationContext")
    return getattr(annotation, "__name__", None) == "ToolInvocationContext"


class FunctionToolAdapter:
    """
    Local Python function tool adapter with schema extraction and validation.
    """

    name = "functions"

    def __init__(
        self,
        *,
        name: str = "functions",
        functions: list[Callable] | dict[str, Callable] | None = None,
        tools_requiring_permission: list[str] | None = None,
    ):
        self.name = name
        self._functions: dict[str, Callable] = {}
        if isinstance(functions, dict):
            self._functions = dict(functions)
        elif functions:
            for func in functions:
                self._functions[func.__name__] = func
        self._tools_requiring_permission = set(tools_requiring_permission or [])
        self._arg_models: dict[str, type[BaseModel]] = {}
        self._accepts_context: dict[str, bool] = {}
        self._tools: dict[str, ToolSpec] = {}
        self._setup_complete = False
        self.loop = LoopRegistry.get_loop()

    async def setup(self) -> None:
        self._tools.clear()
        for fname, func in self._functions.items():
            sig = inspect.signature(func)
            fields: dict[str, tuple[Any, Any]] = {}
            accepts_context = False
            for arg_name, param in sig.parameters.items():
                ann = param.annotation if param.annotation is not inspect._empty else Any
                if _is_context_param(arg_name, ann):
                    accepts_context = True
                    continue
                default = param.default if param.default is not inspect._empty else ...
                fields[arg_name] = (ann, default)
            model_name = f"{fname}_Arguments"
            arg_model = create_model(model_name, __base__=BaseModel, **fields)
            schema = arg_model.model_json_schema()
            parameters_schema = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
            self._arg_models[fname] = arg_model
            self._accepts_context[fname] = accepts_context
            model_tool_name = f"functions_{fname}"
            self._tools[model_tool_name] = ToolSpec(
                adapter_name=self.name,
                provider_name=None,
                tool_name=fname,
                model_tool_name=model_tool_name,
                description=func.__doc__ or "",
                parameters_schema=parameters_schema,
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
        arg_model = self._arg_models[tool_name]
        validated = arg_model(**(parameters or {}))
        kwargs = validated.model_dump()
        if self._accepts_context.get(tool_name) and context is not None:
            kwargs["context"] = context
        try:
            # Sync tools run inline on the event loop; keep them lightweight/non-blocking.
            result = await func(**kwargs) if asyncio.iscoroutinefunction(func) else func(**kwargs)
            text = str(result)
            return ToolResult(
                content=[{"type": "text", "text": text}],
                raw={"value": text},
            )
        except ToolCancelled:
            raise
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def close(self) -> None:
        return None
