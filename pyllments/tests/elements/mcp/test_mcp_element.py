import pytest

from pyllments.elements import MCPElement, PipeElement
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

    pipe_el = PipeElement(receive_callback=lambda payload: payload.model.tool_list)
    return mcp_el, pipe_el

def test_tool_list(mcp_pipe):
    """Test the tool list output of the MCP element."""
    mcp_el, pipe_el = mcp_pipe
    mcp_el.ports.tool_list_output > pipe_el.ports.pipe_input
    assert pipe_el.received_payloads[0]

