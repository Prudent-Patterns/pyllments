import pytest

from pyllments.elements import MCPElement, PipeElement
from pyllments.payloads import StructuredPayload
from pyllments.logging import setup_logging

setup_logging()

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
    mcp_el.ports.tools_schema_output > pipe_el.ports.pipe_input
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
    pipe_el = PipeElement(receive_callback=lambda p: p.model.call_tools())
    mcp_el.ports.tool_response_output > pipe_el.ports.pipe_input
    pipe_el.ports.pipe_output > mcp_el.ports.tool_request_structured_input

    pipe_el.send_payload(StructuredPayload(data=[
        {
            'name': 'test_mcp_calculate',
            'parameters': {'operation': 'add', 'a': 1, 'b': 2}
        }
    ]))

