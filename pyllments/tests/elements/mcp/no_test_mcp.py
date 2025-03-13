from pyllments.elements.mcp import MCPModel
from pyllments.logging import setup_logging

setup_logging()

def main():
    """Main function to demonstrate MCPModel functionality."""
    print("DEBUG: Entering main")
    mcp_model = MCPModel(mcps={
        'test_mcp': {
            'type': 'script',
            'script': 'test_mcp_server.py',
        },
        'test_mcp2': {
            'type': 'script',
            'script': 'test_mcp_server2.py',
        }
    })
    print("DEBUG: Exiting main")

    print("DEBUG: Entering tool list demonstration")
    tool_list = mcp_model.tool_list  # Assuming this exists
    print(f"DEBUG: Tool list: {tool_list}")
    print("DEBUG: Exiting tool list demonstration")

if __name__ == '__main__':
    main()