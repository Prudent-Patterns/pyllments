import sys
import asyncio
import threading
import atexit
from contextlib import AsyncExitStack
from copy import deepcopy
import signal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import param

from pyllments.base.model_base import Model
from pyllments.serve import LoopRegistry


class MCPModel(Model):
    """A model that handles tool calling with the Model Context Protocol."""
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
                }
            },
            'weather': {
                'type': 'sse',
                'host': 'localhost',
                'port': 1234
            },
            'email': {
                'type': 'mcp_class',
                'class': 'GmailMCP'
            }
        }
        """)

    async_loop = param.Parameter(default=None, doc="""
        The asyncio event loop to use for the MCP servers.
        """)
    mcp_loop = param.Parameter(default=None, doc="""
        The asyncio event loop to use for the MCP servers.
        """)
    mcp_thread = param.Parameter(default=None, doc="""
        The thread to use for the MCP servers.
        """)
    context_stack = param.Parameter(default=None, doc="""
        The context stack to use for the MCP servers.
        """)
    
    tool_list = param.List(default=[], instantiate=True, doc="""
        Derived from the MCPs and their tools.
        [{
            'name': 'mcp_name_tool_name',
            'description': 'Tool description',
            'inputSchema': {
                'type': 'object',
                'properties': {'property': {'type': 'string'}},
        },]
    """)
    def __init__(self, **params):
        super().__init__(**params)
        self.async_loop = LoopRegistry.get_loop()
        self.mcps = deepcopy(self.mcps)
        
        # Create a new event loop for MCP sessions
        self.mcp_loop = asyncio.new_event_loop()
        self.setup_complete = threading.Event()
        self._shutdown_requested = False
        
        # Start the MCP thread
        self.mcp_thread = threading.Thread(target=self.run_mcp_loop)
        self.mcp_thread.start()
        
        # Wait for MCP setup to complete before setting up tools
        self.setup_complete.wait()
        self.tools_setup()
        
        # Register shutdown handler
        atexit.register(self.shutdown)
        self._register_shutdown_handler()

    def run_mcp_loop(self):
        """Run the MCP event loop in a dedicated thread."""
        print("DEBUG: Entering run_mcp_loop")
        asyncio.set_event_loop(self.mcp_loop)
        
        # Use a single top-level coroutine for the entire lifecycle
        # This ensures all async operations happen in the same task
        self.mcp_loop.run_until_complete(self._main_task())
        print("DEBUG: Exiting run_mcp_loop")

    async def _main_task(self):
        """Main coroutine that handles the entire lifecycle in a single task."""
        print("DEBUG: Starting main task")
        
        # Create the AsyncExitStack in this task
        async with AsyncExitStack() as stack:
            self.context_stack = stack
            
            try:
                # Setup phase
                print("DEBUG: Running mcp_setup")
                await self.mcp_setup(self.mcps)
                self.setup_complete.set()
                
                # Run phase - keep running until shutdown is requested
                print("DEBUG: Entering main loop")
                while not self._shutdown_requested:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"DEBUG: Exception in main task: {e}")
            finally:
                print("DEBUG: Main task completing")
                # No need to explicitly close the AsyncExitStack - it's handled by the async with
        
        print("DEBUG: Main task finished")
        self.mcp_loop.stop()

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
        
        # The key is to ensure these resources are managed by the context stack
        mcp_spec['read_write_streams'] = await self.context_stack.enter_async_context(
            stdio_client(server_params)
        )
        mcp_spec['session'] = await self.context_stack.enter_async_context(
            ClientSession(*mcp_spec['read_write_streams'])
        )
        await mcp_spec['session'].initialize()

    async def _mcp_sse_setup(self, mcp_name, mcp_spec):
        """Setup an SSE-based MCP server."""
        pass

    async def _mcp_class_setup(self, mcp_name, mcp_spec):
        """Setup a class-based MCP server."""
        pass

    def _register_shutdown_handler(self):
        """Register signal handlers for graceful shutdown."""
        loop = self.async_loop  # Main loop
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: self.mcp_loop.call_soon_threadsafe(self.mcp_loop.stop)
            )

    def shutdown(self):
        """Signal the main task to exit."""
        print("DEBUG: Entering shutdown")
        
        if getattr(self, '_shutdown_requested', False):
            print("DEBUG: Already shutting down")
            return
        
        self._shutdown_requested = True
        
        # Wait for the thread to exit (with timeout)
        if hasattr(self, 'mcp_thread') and self.mcp_thread.is_alive():
            print("DEBUG: Waiting for mcp_thread to finish")
            self.mcp_thread.join(timeout=5)
            
            if self.mcp_thread.is_alive():
                print("DEBUG: Warning: MCP thread did not exit within timeout")
            else:
                print("DEBUG: MCP thread exited cleanly")
        
        print("DEBUG: Exiting shutdown")

    def run_in_mcp_loop(self, coro):
        """Run a coroutine in the MCP loop and return its result."""
        future = asyncio.run_coroutine_threadsafe(coro, self.mcp_loop)
        return future.result()
    
    def create_tool_list_from_mcp(self, mcp_name):
        """Create a tool list from an MCP session."""
        session = self.mcps[mcp_name]['session']
        tools = self.run_in_mcp_loop(session.list_tools())
        tool_list = []
        for tool in tools.tools:
            tool_dict = tool.model_dump()
            tool_dict['parameters'] = tool_dict['inputSchema']
            del tool_dict['inputSchema']
            tool_dict['name'] = f"{mcp_name}_{tool_dict['name']}"
            tool_list.append(tool_dict)
        return tool_list
    
    def tools_setup(self):
        """Set up the tool list from all MCP sessions."""
        tool_list = []
        for mcp_name in self.mcps:
            mcp_tool_list = self.create_tool_list_from_mcp(mcp_name)
            tool_list.extend(mcp_tool_list)
        self.tool_list = tool_list
