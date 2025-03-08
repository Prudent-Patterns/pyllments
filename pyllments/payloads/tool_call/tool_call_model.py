import param

from pyllments.base.model_base import Model


class ToolCallModel(Model):
    """
    Model representing a tool call.
    """
    tool_calls = param.Dict(default=None, doc="""
        The tool call(s).
        {
            'weather_mcp': {
                'tool_a': {'location': 'San Francisco', 'date': '2025-03-05'},
            },
            'todo_mcp': {
                'tool_a': {'task': 'Buy groceries', 'due_date': '2025-03-06'},
            }
        }""")
    
    