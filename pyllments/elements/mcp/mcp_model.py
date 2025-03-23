import sys
import asyncio
import threading
import atexit
from contextlib import AsyncExitStack
from copy import deepcopy
import signal

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import param

from pyllments.base.model_base import Model
from pyllments.common.loop_registry import LoopRegistry


class MCPModel(Model):
    """
    A model that handles tool calling with the Model Context Protocol.
    WARNING: May need to manually run the shutdown() method to gracefully
    exit the servers.
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
            },
            'weather': {
                'type': 'sse',
                'host': 'localhost',
                'port': 1234
            },
            'email': {
                'type': 'mcp_class',
                'class': 'GmailMCP',
                'hitl_tools': ['send_email', 'block_sender']
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
    
    tools = param.Dict(default={}, instantiate=True, doc="""
        Derived from the MCPs and their tools. 
        Dictionary mapping hybrid tool names (mcp_name_tool_name) to their tool definitions.
        {
            'mcp_name_tool_name': {
                'description': 'Tool description',
                'parameters': {
                    'type': 'object',
                    'properties': {'property': {'type': 'string'}},
                }
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
    
    def __init__(self, **params):
        super().__init__(**params)
        self.async_loop = LoopRegistry.get_loop()
        self.mcps = deepcopy(self.mcps)
        
        # Create a new event loop for MCP sessions
        self.mcp_loop = asyncio.new_event_loop()
        self.setup_complete = threading.Event()
        
        # Create an asyncio.Event instead of a boolean flag
        self._shutdown_event = None  # Will be created in the asyncio thread
        
        # Start the MCP thread
        self.mcp_thread = threading.Thread(target=self.run_mcp_loop, daemon=True)
        self.mcp_thread.start()
        
        # Wait for MCP setup to complete before setting up tools
        self.setup_complete.wait()
        self.tools_setup()
        
        # Register shutdown handler
        atexit.register(self.shutdown)
        self._register_shutdown_handler()

    def run_mcp_loop(self):
        """Run the MCP event loop in a dedicated thread."""
        logger.debug("Entering run_mcp_loop")
        asyncio.set_event_loop(self.mcp_loop)
        
        # Use a single top-level coroutine for the entire lifecycle
        # This ensures all async operations happen in the same task
        self.mcp_loop.run_until_complete(self._main_task())
        logger.debug("Exiting run_mcp_loop")

    async def _main_task(self):
        """Main coroutine that handles the entire lifecycle in a single task."""
        logger.info("Starting main task")
        
        # Create the shutdown event in the asyncio thread
        self._shutdown_event = asyncio.Event()
        
        # Create the AsyncExitStack in this task
        async with AsyncExitStack() as stack:
            self.context_stack = stack
            
            try:
                # Setup phase
                logger.debug("Running mcp_setup")
                await self.mcp_setup(self.mcps)
                self.setup_complete.set()
                
                # Wait efficiently for shutdown signal
                logger.debug("Waiting for shutdown signal")
                await self._shutdown_event.wait()
                logger.info("Shutdown signal received")
                
            except Exception as e:
                logger.debug(f"Exception in main task: {e}")
            finally:
                logger.info("Main task completing")
                # AsyncExitStack cleanup handled by async with
        
        logger.info("Main task finished")
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
        logger.info("Entering shutdown")
        
        # Check if already shutting down
        if getattr(self, '_shutdown_in_progress', False):
            logger.debug("Already shutting down")
            return
        self._shutdown_in_progress = True
        
        # Signal the asyncio event from the main thread
        if hasattr(self, '_shutdown_event') and self._shutdown_event is not None:
            logger.info("Setting shutdown event")
            self.mcp_loop.call_soon_threadsafe(self._shutdown_event.set)
        
        # Wait for the thread to exit
        if hasattr(self, 'mcp_thread') and self.mcp_thread.is_alive():
            logger.debug("Waiting for mcp_thread to finish")
            self.mcp_thread.join(timeout=5)
            
            if self.mcp_thread.is_alive():
                logger.debug("Warning: MCP thread did not exit within timeout")
            else:
                logger.info("MCP thread exited cleanly")
        
        logger.info("Exiting shutdown")

    def run_in_mcp_loop(self, coro):
        """Run a coroutine in the MCP loop and return its result."""
        future = asyncio.run_coroutine_threadsafe(coro, self.mcp_loop)
        return future.result()
    
    def create_tools_from_mcp(self, mcp_name):
        """Create a tool dictionary from an MCP session."""
        session = self.mcps[mcp_name]['session']
        tools = self.run_in_mcp_loop(session.list_tools())
        tool_dict = {}
        for tool in tools.tools:
            tool_item = tool.model_dump()
            tool_item['parameters'] = tool_item['inputSchema']
            del tool_item['inputSchema']
            vanilla_name = tool_item['name']
            hybrid_name = f"{mcp_name}_{vanilla_name}"
            # Don't store the name in the value since it's already the key
            del tool_item['name']
            self.hybrid_name_mcp_tool_map[hybrid_name] = {
                'mcp_name': mcp_name,
                'tool_name': vanilla_name
            }
            tool_dict[hybrid_name] = tool_item
        return tool_dict
    
    def tools_setup(self):
        """Set up the tool dictionary from all MCP sessions."""
        tool_dict = {}
        for mcp_name in self.mcps:
            mcp_tool_dict = self.create_tools_from_mcp(mcp_name)
            tool_dict.update(mcp_tool_dict)
        self.tools = tool_dict

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
        def call():
            return self.run_in_mcp_loop(session.call_tool(tool_name, arguments=parameters))
        return call
        
        
