import param
import jinja2
from pyllments.base.model_base import Model


class ToolResponseModel(Model):
    """
    Model representing a tool response.
    """
    tool_responses = param.Dict(default=None, doc="""
        The tool response(s). Metadata from the MCP SDK
        {
            'weather_temp_mcp': {
                'meta': None,
                'content': [{
                    'type': 'text',
                    'text': 'The temperature is 54F.',
                    'annotations': None
                }],
                'isError': False
            },
            'todo_mcp': {
                'meta': None,
                'content': [{
                    'type': 'text',
                    'text': 'Buy Groceries.',
                    'annotations': None
                }],
                'isError': False
            }
        }""")
    
    tool_calls = param.List(doc="""List of functions to call to retrieve the tool responses
    """)
    # content = param.String(default=None, doc="""
    #     String representation of the tool response.""")

    # template = param.ClassSelector(default=None, class_=jinja2.Template)
    # response_specificity = param.Selector(default='default', objects=['default', 'verbose'], doc="""
    #     The specificity with which to construct the str content of the tool response.
    #     'default': 
    #         weather_mcp:
    #             general_weather: sunny
    #             temperature: 54F
    #             wind: 10mph NW wind
    #     """)

    jinja_env = param.ClassSelector(default=None, class_=jinja2.Environment)

    def __init__(self, **params):
        super().__init__(**params)
        # self.jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader('.'))
        # self.template = self.get_template_str()
         
    def call_tools(self):
        for tool_call in self.tool_calls:
            self.tool_responses
    # def get_template_str(self):

    #     if self.response_specificity == 'default':
    #         return self.jinja_env.get_template(self.response_specificity + '.jinja')

    # def render_content(self):
    #     self.content = self.template.render(self.tool_response)