import sys
import asyncio
import atexit
from contextlib import AsyncExitStack
from copy import deepcopy
import signal
import os
import subprocess

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import param

from pyllments.base.model_base import Model
from pyllments.common.loop_registry import LoopRegistry


class MCPModel(Model):
    """
    A model that handles tool calling with the Model Context Protocol.
    
    This model starts child processes for MCP servers and maintains connections
    to them through asyncio. It provides automatic shutdown handling to ensure
    all child processes are terminated when the main process exits.
    
    Shutdown Process:
    1. Attempts graceful shutdown by signaling the main asyncio task to exit
    2. If that fails, forcefully terminates child processes with SIGKILL
    3. Uses multiple fallback mechanisms to ensure processes are terminated
    
    Note: The model is now fully async and runs in the main event loop.
    """
    mcps = param.Dict(default={}, doc="""
        A dictionary mapping server names to their corresponding MCP server specs.
        e.g.
        mcps = {
            'todo': {
                'type': 'script',
                'command': 'python', # Optional, defaults to sys.executable. Can also be 'npx' for JS
                'script': 'todo_server.py',
                'args': ['--logging'],
                'env': {
                    'muh_api_key': 'verynice'
                },
                'tools_requiring_permission': ['remove_todo']
            },
            'weather': {
                'type': 'sse',
                'host': 'localhost',
                'port': 1234
            },
            'functions': {
                'tools': ['custom_fn0', 'custom_fn1'],
                'tools_requiring_permission': ['custom_fn1']
            }
        }
        """)

    tools = param.Dict(default={}, instantiate=True, doc="""
        Derived from the MCPs and their tools. 
        Dictionary mapping hybrid tool names (mcp_name_tool_name) to their tool definitions.
        {
            'mcp_name_tool_name': {
                'description': 'Tool description',
                'parameters': {
                    'type': 'object',
                    'properties': {'property': {'type': 'string'}},
                },
                'permission_required': True
            },
        }
    """)

    hybrid_name_mcp_tool_map = param.Dict(default={}, instantiate=True, doc="""
        A dictionary mapping hybrid tool names to their corresponding MCP name and tool name
        e.g.
        hybrid_name_mcp_tool_map = {
            'test_mcp_calculate': {
                'mcp_name': 'test_mcp',
                'tool_name': 'calculate'
            }
        }
        """)
    
    loop = param.Parameter(default=None, doc="The event loop to use for setup.")
    
    def __init__(self, **params):
        super().__init__(**params)
        self.mcps = deepcopy(self.mcps)
        self.context_stack = AsyncExitStack()
        self._child_processes = []
        atexit.register(self._force_kill_processes)
        # Start async setup in background
        self.loop = LoopRegistry.get_loop()
        self._setup_task = self.loop.create_task(self.setup())
        self._setup_complete = False

    async def setup(self):
        """Async setup for MCP servers and tools. Call this after instantiation."""
        await self.context_stack.__aenter__()
        await self.mcp_setup(self.mcps)
        await self.tools_setup()
        self._setup_complete = True
        logger.info("MCPModel setup complete")

    async def await_ready(self):
        """Await until the model setup is complete."""
        if not self._setup_complete:
            await self._setup_task
        return self

    async def mcp_setup(self, mcps):
        """Set up the MCP servers and clients."""
        for mcp_name in mcps.keys():
            mcp_spec = mcps[mcp_name]
            if mcp_spec['type'] == 'script':
                await self._mcp_script_setup(mcp_name)
            elif mcp_spec['type'] == 'sse':
                await self._mcp_sse_setup(mcp_name)
            elif mcp_spec['type'] == 'mcp_class':
                await self._mcp_class_setup(mcp_name)

    async def _mcp_script_setup(self, mcp_name):
        """Set up a script-based MCP server."""
        mcp_spec = self.mcps[mcp_name]
        script = mcp_spec['script']
        if script.endswith('.py'):
            command = mcp_spec.get('command', sys.executable)
        elif script.endswith('.js'):
            command = 'npx'
        else:
            raise ValueError(f"Unsupported script type: {script}")

        server_params = StdioServerParameters(
            command=command,
            args=[script] + mcp_spec.get('args', []),
            env=mcp_spec.get('env', {})
        )

        mcp_spec['read_write_streams'] = await self.context_stack.enter_async_context(
            stdio_client(server_params)
        )
        mcp_spec['session'] = await self.context_stack.enter_async_context(
            ClientSession(*mcp_spec['read_write_streams'])
        )
        await mcp_spec['session'].initialize()

        # Store process for forced termination
        if hasattr(mcp_spec['read_write_streams'], 'process'):
            self._child_processes.append(mcp_spec['read_write_streams'].process)

    async def _mcp_sse_setup(self, mcp_name, mcp_spec):
        pass

    async def _mcp_class_setup(self, mcp_name, mcp_spec):
        pass

    async def create_tools_from_mcp(self, mcp_name):
        """Create a tool dictionary from an MCP session."""
        session = self.mcps[mcp_name]['session']
        tools = await session.list_tools()
        tool_dict = {}
        for tool in tools.tools:
            tool_item = tool.model_dump()
            tool_item['parameters'] = tool_item['inputSchema']
            del tool_item['inputSchema']
            vanilla_name = tool_item['name']
            # Determine if this tool requires permission based on mcps config
            permission_required = False
            required_tools = self.mcps.get(mcp_name, {}).get('tools_requiring_permission', [])
            if vanilla_name in required_tools:
                permission_required = True
            tool_item['permission_required'] = permission_required
            hybrid_name = f"{mcp_name}_{vanilla_name}"
            del tool_item['name']
            self.hybrid_name_mcp_tool_map[hybrid_name] = {
                'mcp_name': mcp_name,
                'tool_name': vanilla_name
            }
            tool_dict[hybrid_name] = tool_item
        return tool_dict

    async def tools_setup(self):
        """Set up the tool dictionary from all MCP sessions."""
        tool_dict = {}
        for mcp_name in self.mcps:
            mcp_tool_dict = await self.create_tools_from_mcp(mcp_name)
            tool_dict.update(mcp_tool_dict)
        self.tools = tool_dict
        logger.debug(f"MCPModel: Tools ready: {list(self.tools.keys())}")

    def create_calls(self, tool_calls: list[dict]):
        call_list = []
        for tool_call in tool_calls:
            call_list.append(
                self.create_call(
                    name=tool_call['name'],
                    parameters=tool_call.get('parameters', None)
                )
            )
        return call_list

    def create_call(self, name: str, parameters: dict | None):
        mcp_tool = self.hybrid_name_mcp_tool_map[name]
        mcp_name = mcp_tool['mcp_name']
        tool_name = mcp_tool['tool_name']
        session = self.mcps[mcp_name]['session']
        async def call():
            return await session.call_tool(tool_name, arguments=parameters)
        return call

    def _force_kill_processes(self):
        """Force kill all child processes at exit."""
        for process in self._child_processes:
            if process and process.poll() is None:
                try:
                    process.kill()
                except:
                    try:
                        os.kill(process.pid, signal.SIGKILL)
                    except:
                        subprocess.run(["kill", "-9", str(process.pid)], 
                                      stderr=subprocess.DEVNULL, 
                                      stdout=subprocess.DEVNULL)

    async def close(self):
        # Call this when you're done with the model
        await self.context_stack.__aexit__(None, None, None)
        
        
