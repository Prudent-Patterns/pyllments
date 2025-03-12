import unittest

from pyllments.elements.mcp import MCPModel


class TestMCPModel(unittest.TestCase):
    def setUp(self):
        print("DEBUG: Entering setUp")
        self.mcp_model = MCPModel(mcps={
            'test_mcp': {
                'type': 'script',
                'script': 'test_mcp_server.py',
            }
        })
        print("DEBUG: Exiting setUp")

    def test_tool_list(self):
        print("DEBUG: Entering test_tool_list")
        tool_list = self.mcp_model.tool_list  # Assuming this exists
        print(f"DEBUG: Tool list: {tool_list}")
        print("DEBUG: Exiting test_tool_list")

    def tearDown(self):
        print("DEBUG: Entering tearDown")
        self.mcp_model.shutdown()
        print("DEBUG: Exiting tearDown")

if __name__ == '__main__':
    print("DEBUG: Starting unittest")
    unittest.main()
    print("DEBUG: unittest completed")