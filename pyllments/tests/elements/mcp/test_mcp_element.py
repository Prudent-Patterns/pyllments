import pytest

from pyllments.elements.mcp import MCPElement
from pyllments.logging import setup_logging

setup_logging()

@pytest.fixture
def mcp_element():
    """Fixture to create an instance of MCPElement for testing."""
    print("DEBUG: Entering fixture setup")
    element = MCPElement(mcps={
        'test_mcp': {
            'type': 'script',
            'script': 'test_mcp_server.py',
        },
        'test_mcp2': {
            'type': 'script',
            'script': 'test_mcp_server2.py',
        }
    })
    print("DEBUG: Exiting fixture setup")
    return element

def test_tool_list_emit(mcp_element):
    """Test the tool list emission functionality."""
    print("DEBUG: Entering test_tool_list_emit")
    # Add assertions and test logic here
