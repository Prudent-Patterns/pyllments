from __future__ import annotations

import asyncio
import atexit
import os
import signal
import subprocess
import sys
from contextlib import AsyncExitStack
from copy import deepcopy
from pathlib import Path
from typing import Any

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pyllments.runtime.lifecycle_manager import manager as lifecycle_manager
from pyllments.runtime.loop_registry import LoopRegistry

from .tool_adapter import ToolError, ToolResult, ToolSpec


class MCPToolAdapter:
    """
    MCP-backed tool adapter owning session lifecycle and tool discovery.
    """

    name = "mcp"

    def __init__(self, *, name: str = "mcp", mcps: dict | None = None):
        self.name = name
        self.mcps = deepcopy(mcps or {})
        self._context_stack = AsyncExitStack()
        self._child_processes: list = []
        self._setup_complete = False
        self._model_tool_map: dict[str, dict[str, str]] = {}
        self._tools: dict[str, ToolSpec] = {}
        self.loop = LoopRegistry.get_loop()
        atexit.register(self._force_kill_processes)
        lifecycle_manager.register_resource(self)

    async def setup(self) -> None:
        await self._context_stack.__aenter__()
        for mcp_name, spec in self.mcps.items():
            if spec.get("type") == "script":
                await self._mcp_script_setup(mcp_name)
            elif spec.get("type") == "sse":
                await self._mcp_sse_setup(mcp_name)
            elif spec.get("type") == "mcp_class":
                await self._mcp_class_setup(mcp_name)
        await self._discover_tools()
        self._setup_complete = True
        logger.bind(name=self.__class__.__name__).info("MCPToolAdapter setup complete")

    async def await_ready(self):
        if not self._setup_complete:
            await self.setup()
        return self

    async def list_tools(self) -> dict[str, ToolSpec]:
        await self.await_ready()
        return dict(self._tools)

    def resolve_model_tool_name(self, model_tool_name: str) -> tuple[str | None, str]:
        mapping = self._model_tool_map.get(model_tool_name)
        if mapping is None:
            raise KeyError(f"Unknown model tool name: {model_tool_name}")
        return mapping["provider_name"], mapping["tool_name"]

    async def call_tool(
        self,
        *,
        provider_name: str | None,
        tool_name: str,
        parameters: dict | None,
    ) -> ToolResult:
        await self.await_ready()
        if provider_name is None:
            raise ValueError("MCP tool calls require provider_name")
        session = self.mcps[provider_name]["session"]
        try:
            response = await session.call_tool(tool_name, arguments=parameters or {})
            dumped = response.model_dump() if hasattr(response, "model_dump") else response
            content = dumped.get("content", []) if isinstance(dumped, dict) else []
            if dumped.get("isError"):
                raise RuntimeError(
                    content[0].get("text", "MCP tool error") if content else "MCP tool error"
                )
            return ToolResult(content=content, raw=dumped)
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    async def close(self) -> None:
        await self._context_stack.__aexit__(None, None, None)
        self._force_kill_processes()

    async def _discover_tools(self):
        self._tools.clear()
        self._model_tool_map.clear()
        for mcp_name, spec in self.mcps.items():
            if spec.get("type") == "functions":
                continue
            session = spec.get("session")
            if session is None:
                continue
            tools = await session.list_tools()
            required = spec.get("tools_requiring_permission", [])
            for tool in tools.tools:
                tool_item = tool.model_dump()
                vanilla_name = tool_item["name"]
                parameters = tool_item.get("inputSchema", {})
                model_tool_name = f"{mcp_name}_{vanilla_name}"
                self._model_tool_map[model_tool_name] = {
                    "provider_name": mcp_name,
                    "tool_name": vanilla_name,
                }
                self._tools[model_tool_name] = ToolSpec(
                    adapter_name=self.name,
                    provider_name=mcp_name,
                    tool_name=vanilla_name,
                    model_tool_name=model_tool_name,
                    description=tool_item.get("description", ""),
                    parameters_schema=parameters,
                    permission_required=vanilla_name in required,
                )

    async def _mcp_script_setup(self, mcp_name: str):
        mcp_spec = self.mcps[mcp_name]
        script_path = Path(mcp_spec["script"]).expanduser().resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found for MCP '{mcp_name}': {script_path}")
        if script_path.suffix == ".py":
            command = mcp_spec.get("command", sys.executable)
        elif script_path.suffix == ".js":
            command = "npx"
        else:
            raise ValueError(f"Unsupported script type: {script_path.suffix}")

        server_params = StdioServerParameters(
            command=command,
            args=[str(script_path)] + mcp_spec.get("args", []),
            env=mcp_spec.get("env", {}),
        )
        mcp_spec["read_write_streams"] = await self._context_stack.enter_async_context(
            stdio_client(server_params)
        )
        mcp_spec["session"] = await self._context_stack.enter_async_context(
            ClientSession(*mcp_spec["read_write_streams"])
        )
        await mcp_spec["session"].initialize()
        if hasattr(mcp_spec["read_write_streams"], "process"):
            self._child_processes.append(mcp_spec["read_write_streams"].process)

    async def _mcp_sse_setup(self, mcp_name: str):
        pass

    async def _mcp_class_setup(self, mcp_name: str):
        pass

    def _force_kill_processes(self):
        for process in self._child_processes:
            if process and process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    try:
                        os.kill(process.pid, signal.SIGKILL)
                    except Exception:
                        subprocess.run(
                            ["kill", "-9", str(process.pid)],
                            stderr=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                        )
