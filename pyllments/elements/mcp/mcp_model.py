import sys
import asyncio
import atexit
from contextlib import AsyncExitStack
from copy import deepcopy
import signal
import os
import subprocess
import inspect
from typing import Any, Dict, List
from pydantic import BaseModel, create_model
from pathlib import Path
import concurrent.futures
import functools

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import param

from pyllments.base.model_base import Model
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.runtime.lifecycle_manager import manager as lifecycle_manager

# Wrapper to ensure our Python function calls return a Pydantic model with model_dump()
class PythonToolResponse(BaseModel):
    meta: Any
    content: List[Dict[str, Any]]
    isError: bool

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
    A dictionary mapping server names to their MCP configurations. Each configuration dict may include the following keys:

    - type (str): Protocol type; one of 'script', 'sse', 'mcp_class', or 'functions'.
    - script (str, optional): Path to the script to execute for 'script' type.
    - command (str, optional): Executable to run the script (defaults to the Python interpreter).
    - args (list[str], optional): Command-line arguments for the script.
    - env (dict, optional): Environment variables for the subprocess.
    - host (str, optional): Host address for 'sse' type servers.
    - port (int, optional): Port number for 'sse' type servers.
    - tools (dict[str, Callable], optional): Mapping of function names to Python callables for 'functions' type.
    - tools_requiring_permission (list[str], optional): List of tool names that require user permission.

    Example:
    mcps = {
        'todo': {
            'type': 'script',
            'script': 'todo_server.py',
            'command': 'python',
            'args': ['--logging'],
            'env': {'API_KEY': 'xyz'},
            'tools_requiring_permission': ['remove_todo']
        },
        'weather': {
            'type': 'sse',
            'host': 'localhost',
            'port': 1234
        },
        'custom_funcs': {
            'type': 'functions',
            'tools': {
                'calculate': calculate,
                'get_current_time': get_current_time
            },
            'tools_requiring_permission': ['calculate']
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
        # Shared thread pool for executing sync tools efficiently
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=os.cpu_count() or 4,
            thread_name_prefix=f"{self.__class__.__name__}-tool-exec"
        )
        atexit.register(self._force_kill_processes)
        # Start async setup in background
        self.loop = LoopRegistry.get_loop()
        # Register this model for automatic cleanup on shutdown
        lifecycle_manager.register_resource(self)
        self._setup_task = self.loop.create_task(self.setup())
        self._setup_complete = False

    async def setup(self):
        """Async setup for MCP servers and tools. Call this after instantiation."""
        await self.context_stack.__aenter__()
        await self.mcp_setup(self.mcps)
        await self.tools_setup()
        self._setup_complete = True
        self.logger.info("MCPModel setup complete")

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
        # Canonicalize and validate script path
        script_path = Path(script).expanduser().resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found for MCP '{mcp_name}': {script_path}")
        # Determine executor based on file suffix
        if script_path.suffix == '.py':
            command = mcp_spec.get('command', sys.executable)
        elif script_path.suffix == '.js':
            command = 'npx'
        else:
            raise ValueError(f"Unsupported script type: {script_path.suffix}")

        server_params = StdioServerParameters(
            command=command,
            args=[str(script_path)] + mcp_spec.get('args', []),
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

    async def create_tools_from_functions(self, mcp_name: str) -> dict[str, dict]:
        """Dynamically build Pydantic arg models and schemas for Python functions."""
        spec = self.mcps[mcp_name]
        callables = spec.get('tools', {})
        perms = spec.get('tools_requiring_permission', [])
        tool_dict: dict[str, dict] = {}
        for fname, orig_func in callables.items():
            # Capture original signature for argument model
            sig = inspect.signature(orig_func)
            # Wrap synchronous functions so they behave asynchronously via the shared executor
            if not asyncio.iscoroutinefunction(orig_func):
                async def _async_wrapper(*args, _orig=orig_func, **kwargs):
                    bound_fn = functools.partial(_orig, *args, **kwargs)
                    return await self.loop.run_in_executor(self._executor, bound_fn)
                _async_wrapper.__name__ = orig_func.__name__
                _async_wrapper.__doc__ = orig_func.__doc__
                wrapped = _async_wrapper
            else:
                wrapped = orig_func
            hybrid = f"{mcp_name}_{fname}"
            # Build dynamic Pydantic model for arguments using the original function's signature
            fields: dict[str, tuple[Any, Any]] = {}
            for arg_name, p in sig.parameters.items():
                ann = p.annotation if p.annotation is not inspect._empty else Any
                default = p.default if p.default is not inspect._empty else ...
                fields[arg_name] = (ann, default)
            # Name the Pydantic model uniquely to avoid collisions across MCPs
            model_name = f"{mcp_name}_{orig_func.__name__}_Arguments"
            arg_model = create_model(model_name, __base__=BaseModel, **fields)
            schema = arg_model.model_json_schema()
            params = {
                'properties': schema.get('properties', {}),
                'required': schema.get('required', []),
                'title': schema.get('title', model_name),
                'type': 'object'
            }
            self.hybrid_name_mcp_tool_map[hybrid] = {'mcp_name': mcp_name, 'tool_name': fname}
            tool_dict[hybrid] = {
                'description': orig_func.__doc__ or '',
                'parameters': params,
                'permission_required': fname in perms,
                'func': wrapped,
                'arg_model': arg_model
            }
        return tool_dict

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
        """Aggregate tools from MCP sessions and Pydantic-validated Python functions."""
        combined: dict[str, dict] = {}
        for name, spec in self.mcps.items():
            if spec.get('type') == 'functions':
                part = await self.create_tools_from_functions(name)
            else:
                part = await self.create_tools_from_mcp(name)
            combined.update(part)
        self.tools = combined
        self.logger.debug(f"MCPModel: Tools ready: {list(self.tools.keys())}")

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
        tool_data = self.tools[name]
        # Inline Pydantic argument validation for Python function tools
        if 'arg_model' in tool_data:
            func = tool_data['func']
            arg_model = tool_data['arg_model']
            async def call():
                try:
                    # Validate and coerce inputs via Pydantic
                    validated = arg_model(**(parameters or {}))
                    kwargs = validated.dict()
                    # Execute the function (sync or async)
                    if asyncio.iscoroutinefunction(func):
                        result = await func(**kwargs)
                    else:
                        # Offload sync function to a thread to avoid blocking the main event loop
                        result = await asyncio.to_thread(func, **kwargs)
                    text = str(result)
                    # Wrap in a Pydantic model so .model_dump() works
                    return PythonToolResponse(
                        meta=None,
                        content=[{'type': 'text', 'text': text, 'annotations': None}],
                        isError=False
                    )
                except Exception as e:
                    return PythonToolResponse(
                        meta=None,
                        content=[{'type': 'text', 'text': repr(e), 'annotations': None}],
                        isError=True
                    )
            return call
        # Existing MCP session tool
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
        """Clean up MCPModel: exit context stack, kill processes, and shut down executor."""
        # Exit async context (closes client sessions)
        await self.context_stack.__aexit__(None, None, None)
        # Force kill any remaining child processes
        try:
            self._force_kill_processes()
        except Exception as e:
            self.logger.error(f"Error in force-kill processes: {e}")
        # Shutdown thread pool executor
        try:
            self._executor.shutdown(wait=True)
        except Exception as e:
            self.logger.error(f"Error shutting down executor: {e}")
        
        
