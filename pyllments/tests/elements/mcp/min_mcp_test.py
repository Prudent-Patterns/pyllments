#!/usr/bin/env python3
"""
Minimal test for MCP connectivity using the same libraries as MCPModel
but with a more direct approach to isolate where hangs might occur.
"""

import asyncio
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pyllments.serve import LoopRegistry

server_params = StdioServerParameters(
    command="python", # Executable
    args=["test_mcp_server.py"], # Optional command line arguments
    env=None # Optional environment variables
)
loop = LoopRegistry.get_loop()

context_stack = AsyncExitStack()
read, write = loop.run_until_complete(context_stack.enter_async_context(stdio_client(server_params)))
session = loop.run_until_complete(context_stack.enter_async_context(ClientSession(read, write)))

loop.run_until_complete(session.initialize())

print(loop.run_until_complete(session.list_tools()))

# if __name__ == "__main__":
#     main()
