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

def test_tools(mcp_model):
    """Test the tools functionality."""
    print("DEBUG: Entering test_tools")
    tools = mcp_model.tools  # Now using the new property name
    print(f"DEBUG: Tools: {tools}")
    print("DEBUG: Exiting test_tools")

