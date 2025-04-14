import pytest
import asyncio
import time  # Import time

from pyllments.elements import MCPElement, PipeElement
from pyllments.payloads import StructuredPayload
from pyllments.logging import setup_logging
from loguru import logger
from pyllments.common.loop_registry import LoopRegistry # Import LoopRegistry
setup_logging()

# Helper function to run the loop
def run_loop_briefly(loop, duration=0.1):
    stop_time = loop.time() + duration
    while loop.time() < stop_time:
        loop.run_until_complete(asyncio.sleep(0.01)) # Allow tasks to run

@pytest.fixture
def mcp_pipe():
    """Fixture to create an instance of MCPElement for testing."""
    mcp_el = MCPElement(mcps={
        'test_mcp': {
            'type': 'script',
            'script': 'test_mcp_server.py',
        },
        'test_mcp2': {
            'type': 'script',
            'script': 'test_mcp_server2.py',
        }
    })

    pipe_el = PipeElement(receive_callback=lambda payload: payload.model.schema.model_json_schema())
    return mcp_el, pipe_el

def test_tool_list(mcp_pipe):
    """Test the tool list output of the MCP element."""
    mcp_el, pipe_el = mcp_pipe
    loop = LoopRegistry.get_loop() # Get the loop

    mcp_el.ports.tools_schema_output > pipe_el.ports.pipe_input
    
    # Run the loop to allow connection and emission
    run_loop_briefly(loop, duration=0.2)

    assert len(pipe_el.received_payloads) > 0 # Check if any payload was received
    assert pipe_el.received_payloads[0]

def test_tool_response():
    mcp_el = MCPElement(mcps={
        'test_mcp': {
            'type': 'script',
            'script': 'test_mcp_server.py',
        },
        'test_mcp2': {
            'type': 'script',
            'script': 'test_mcp_server2.py',
        }
    })
    # pipe_el = PipeElement(receive_callback=lambda p: p.model.call_tools())
    pipe_el = PipeElement(receive_callback=lambda p: p.model.call_tools())
    loop = LoopRegistry.get_loop() # Get the loop

    mcp_el.ports.tool_response_output > pipe_el.ports.pipe_input
    pipe_el.ports.pipe_output > mcp_el.ports.tool_request_structured_input

    # Run loop to allow connections to establish
    run_loop_briefly(loop, duration=0.1)

    # send_payload is now synchronous, but schedules async work
    pipe_el.send_payload(StructuredPayload(data=[
        {
            'name': 'test_mcp_calculate',
            'parameters': {'operation': 'add', 'a': 1, 'b': 2}
        }
    ]))

    # Run the loop to allow send/receive/process
    run_loop_briefly(loop, duration=0.2)

    assert len(pipe_el.received_payloads) > 0 # Check if any payload was received
    logger.info(f"Pipe Element Received Payload: {pipe_el.received_payloads[0].model.content}")    # pipe_el.receive_callback = lambda payload: payload.model.content

    # pipe_el.send_payload(StructuredPayload(data=[
    #     {
    #         'name': 'test_mcp_calculate',
    #         'parameters': {'operation': 'add', 'a': 1, 'b': 2}
    #     }
    # ]))
