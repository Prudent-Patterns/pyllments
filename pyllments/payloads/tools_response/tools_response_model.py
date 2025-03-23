import param
import jinja2
from pyllments.base.model_base import Model


class ToolsResponseModel(Model):
    """
    Model representing a tool response.
    """
    _content = param.String(default=None, doc="""
        The string representation of the tool response.
        """)
    tool_responses = param.Dict(default=None, doc="""
        The tool response(s). Response from the MCP SDK
        {
            'weather_temp_mcp': {
                'mcp_name': 'weather_mcp',
                'tool_name': 'temp',
                'description': 'Get the temperature in a location',
                'parameters': {'location': 'San Francisco'}, # parameters of the tool call
                'response': {
                    'meta': None,
                    'content': [{
                        'type': 'text',
                        'text': 'The temperature is 54F.',
                        'annotations': None
                    }],
                    'isError': False
                }
            },
            'todo_mcp': {
                'mcp_name': 'todo_mcp',
                'tool_name': 'add',
                'description': 'Add a todo item',
                'parameters': None,
                'response': {
                    'meta': None,
                     'content': [{
                        'type': 'text',
                        'text': 'Buy Groceries.',
                        'annotations': None
                    }],
                    'isError': False
                }
            }
        }""")
    
    tool_calls = param.List(doc="""List of functions to call to retrieve the tool responses
    """)

    template = param.ClassSelector(default=None, class_=jinja2.Template)
    # response_specificity = param.Selector(default='default', objects=['default', 'verbose'], doc="""
    #     The specificity with which to construct the str content of the tool response.
    #     'default': 
    #         weather_mcp:
    #             general_weather: sunny
    #             temperature: 54F
    #             wind: 10mph NW wind
    #     """)

    # jinja_env = param.ClassSelector(default=None, class_=jinja2.Environment)

    def __init__(self, **params):
        super().__init__(**params)
        self.set_template()
        # self.jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader('.'))
        # self.template = self.get_template_str()
    
    @property
    def content(self):
        if not self._content:
            self._content = self.template.render(tool_responses=self.tool_responses)
        return self._content
    
    def set_template(self):
        # Update the template to trim whitespace and reduce extra blank lines
        self.template = jinja2.Template("""{%- for tool_name, tool_data in tool_responses.items() %}
### Tool: {{ tool_name }}
{%- if tool_data.description %}
### Description:
{{ tool_data.description }}
{%- endif %}
{%- if tool_data.parameters %}
### Parameters:
{%- for param_name, param_value in tool_data.parameters.items() %}
- {{ param_name }}: {{ param_value }}
{%- endfor %}
{%- endif %}
### Response:
{%- for content_item in tool_data.response.content %}
{{ content_item.text }}
{%- endfor %}
{%- endfor %}""")
    
    def call_tools(self):
        for tool, tool_spec in self.tool_responses.items():
            tool_spec['response'] = tool_spec['call']().model_dump()
        return self.tool_responses
    # def get_template_str(self):

    #     if self.response_specificity == 'default':
    #         return self.jinja_env.get_template(self.response_specificity + '.jinja')

    # def render_content(self):
    #     self.content = self.template.render(self.tool_response)