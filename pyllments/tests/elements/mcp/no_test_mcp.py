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

    print("DEBUG: Entering tools demonstration")
    tools = mcp_model.tools  # Using the new property name
    print(f"DEBUG: Tools: {tools}")
    print("DEBUG: Exiting tools demonstration")

if __name__ == '__main__':
    main()