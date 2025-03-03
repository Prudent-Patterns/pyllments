import asyncio
from contextlib import AsyncExitStack
from copy import deepcopy

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import param

from pyllments.base.model_base import Model
from pyllments.serve import loop_registry


class MCPModel(Model):
    """A model that handles tool calling with the Model Context Protocol."""
    mcps = param.Dict(default={}, doc="""
        A dictionary mapping server names to their corresponding MCP server specs.
        e.g.
        mcps = {
            'todo': {
                'type': 'script',
                'script': 'todo_server.py',
                'args': ['--logging']
                'env': {
                    'muh_api_key': 'verynice'
                }
            },
            'weather': {
                'type': 'sse'
                'host': 'localhost',
                'port': 1234
            },
            email: {
                'type': 'mcp_class',
                'class': 'GmailMCP'
            }
        }
        """)

    async_loop = param.Parameter(default=None, doc="""
        The asyncio event loop to use for the MCP servers.
        """)
    context_stack = param.Parameter(default=None, doc="""
        The context stack to use for the MCP servers.
        """)

    def __init__(self, **params):
        super().__init__(**params)
        self.async_loop = loop_registry.get_loop()
        self.context_stack = AsyncExitStack()
        self.mcps = deepcopy(self.mcps)
        
        self.mcp_setup(self.mcps)
        self.async_loop.create_task(self.keep_alive())

    def mcp_setup(self, mcps):
        """Setup the MCP servers and clients"""
        for mcp_name, mcp_spec in mcps.items():
            if mcp_spec['type'] == 'script':
                self._mcp_script_setup(mcp_name, mcp_spec)
            elif mcp_spec['type'] == 'sse':
                self._mcp_sse_setup(mcp_name, mcp_spec)
            elif mcp_spec['type'] == 'mcp_class':
                self._mcp_class_setup(mcp_name, mcp_spec)
    
    async def _mcp_script_setup(self, mcp_name):
        """Setup a script-based MCP server."""
        mcp_spec = self.mcps[mcp_name]
        if (script := mcp_spec['script']).endswith('.py'):
            command = 'python'
        elif script.endswith('.js'):
            command = 'npx'
        else:
            raise ValueError(f"Unsupported script type: {script}")

        server_params = StdioServerParameters(
            command=command,
            args=mcp_spec.get('args', []),
            env=mcp_spec.get('env', {})
        )

        mcp_spec['read_write_streams'] = await self.context_stack.enter_async_context(
            stdio_client(server_params)
            )
        mcp_spec['session'] = await ClientSession(*mcp_spec['read_write_streams'])
        await mcp_spec['session'].initialize()

    def _mcp_sse_setup(self, mcp_name, mcp_spec):
        """Setup an SSE-based MCP server."""
        pass

    def _mcp_class_setup(self, mcp_name, mcp_spec):
        """Setup a class-based MCP server."""
        pass

    async def keep_alive(self):
        try:
            await asyncio.Future()  # Keeps stack alive
        except asyncio.CancelledError:
            await self.stack.aclose()
