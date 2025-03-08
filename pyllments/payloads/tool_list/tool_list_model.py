import param
import jinja2
from pyllments.base.model_base import Model

class ToolListModel(Model):
    tools = param.Dict(default={}, doc="""
        A dictionary of MCPs and corresponding tools. The inputSchema is based on the
        JSON schema of the tool returned by the MCP server. Also useful in conjunction
        with the tool/structured output of some LLM providers.
        {
            'weather_mcp': {
                'tools': [
                    {
                        'name': 'get_weather',
                        'description': 'Get the weather for a given location',
                        'inputSchema': {
                            'properties': {
                                'location': {
                                    'title': 'Location',
                                    'type': 'string',
                                }
                            },
                            'required': ['location'],
                            'title': 'get_weatherArguments',
                            'type': 'object'
                       
                        }
                    }
                ]
            }
        }
        """)
    content = param.String(default=None, doc="""
        String representation of the tool list.""")

    template = param.ClassSelector(default=None, class_=jinja2.Template)
    tool_format = param.Selector(default='default', objects=['default', 'verbose'], doc="""
        The format of the tool list.
        'default':
            - weather.get_weather(location: string)
            - todo.add_task(task: string)
        'verbose':
            """)

    def __init__(self, **params):
        super().__init__(**params)
        self.template = self.get_template_str()

    def get_template_str(self):
        if self.tool_format == 'default':
            return self.jinja_env.get_template('default.jinja')
