import pytest

from pyllments.elements.mcp import MCPModel
from pyllments.logging import setup_logging

setup_logging()

@pytest.fixture
def mcp_model():
    """Fixture to create an instance of MCPModel for testing."""
    print("DEBUG: Entering fixture setup")
    model = MCPModel(mcps={
        'test_mcp': {
            'type': 'script',
            'script': 'test_mcp_server.py',
        }
    })
    print("DEBUG: Exiting fixture setup")
    return model

def test_tool_list(mcp_model):
    """Test the tool list functionality."""
    print("DEBUG: Entering test_tool_list")
    tool_list = mcp_model.tool_list  # Assuming this exists
    print(f"DEBUG: Tool list: {tool_list}")
    print("DEBUG: Exiting test_tool_list")

