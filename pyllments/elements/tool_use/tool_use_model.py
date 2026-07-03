from __future__ import annotations

import asyncio
import json
from typing import Any, Literal, Union

import param
from pydantic import BaseModel, Field, RootModel, create_model

from pyllments.base.model_base import Model
from pyllments.common.pydantic_models import CleanModel
from pyllments.payloads import ToolUsePayload
from pyllments.runtime.scheduler import resolve_loop, schedule_task

from .function_tool_adapter import FunctionToolAdapter
from .mcp_tool_adapter import MCPToolAdapter
from .tool_adapter import ToolAdapter, ToolSpec
from .tool_invocation_context import ToolCancelled, ToolInvocationContext


class ToolUseModel(Model):
    """Model backing ToolUseElement adapter orchestration and execution."""

    adapters = param.List(default=[], doc="Registered tool adapters")
    tool_specs = param.Dict(default={}, doc="Aggregated model_tool_name -> ToolSpec")
    _setup_complete = False

    def __init__(self, adapters: list[ToolAdapter] | None = None, **params):
        super().__init__(**params)
        self.adapters = adapters or []
        self.loop = resolve_loop()
        self._setup_task = schedule_task(self.setup())

    async def setup(self):
        for adapter in self.adapters:
            await adapter.setup()
        await self.refresh_tool_specs()
        self._setup_complete = True

    async def await_ready(self):
        if not self._setup_complete:
            await self._setup_task
        return self

    async def refresh_tool_specs(self):
        combined: dict[str, ToolSpec] = {}
        for adapter in self.adapters:
            tools = await adapter.list_tools()
            combined.update(tools)
        self.tool_specs = combined

    def get_adapter(self, adapter_name: str) -> ToolAdapter:
        for adapter in self.adapters:
            if adapter.name == adapter_name:
                return adapter
        raise KeyError(f"Unknown adapter: {adapter_name}")

    def spec_for_model_tool(self, model_tool_name: str) -> ToolSpec:
        spec = self.tool_specs.get(model_tool_name)
        if spec is None:
            raise KeyError(f"Unknown model tool name: {model_tool_name}")
        return spec

    async def execute_tool_use(
        self,
        record: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> dict[str, Any]:
        adapter = self.get_adapter(record["adapter_name"])
        try:
            result = await adapter.call_tool(
                provider_name=record.get("provider_name"),
                tool_name=record["tool_name"],
                parameters=record.get("parameters"),
                context=context,
            )
            return {"result": result.to_dict()}
        except ToolCancelled as exc:
            return {"cancelled": True, "reason": str(exc)}
        except Exception as exc:
            return {
                "error": {
                    "type": "ToolExecutionError",
                    "message": str(exc),
                    "retryable": False,
                    "details": {},
                }
            }

    async def close(self):
        for adapter in self.adapters:
            await adapter.close()


def build_adapters(
    *,
    adapters: list[ToolAdapter] | None = None,
    mcps: dict | None = None,
    functions: list | dict | None = None,
    tools_requiring_permission: list[str] | None = None,
) -> list[ToolAdapter]:
    """Expand convenience params into adapter instances."""
    built: list[ToolAdapter] = list(adapters or [])
    mcp_specs = dict(mcps or {})
    function_specs = {
        name: spec
        for name, spec in mcp_specs.items()
        if spec.get("type") == "functions"
    }
    for name in function_specs:
        mcp_specs.pop(name, None)
    if mcp_specs:
        built.append(MCPToolAdapter(mcps=mcp_specs))
    for name, spec in function_specs.items():
        built.append(
            FunctionToolAdapter(
                name=name,
                functions=spec.get("tools", {}),
                tools_requiring_permission=spec.get("tools_requiring_permission", []),
            )
        )
    if functions:
        built.append(
            FunctionToolAdapter(
                functions=functions,
                tools_requiring_permission=tools_requiring_permission,
            )
        )
    return built
