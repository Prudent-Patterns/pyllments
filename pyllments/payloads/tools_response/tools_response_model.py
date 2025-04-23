import param
import jinja2
import asyncio
import time
from pyllments.base.model_base import Model


class ToolsResponseModel(Model):
    """
    Model representing a tool response.
    """
    timestamp = param.Number(default=None, doc="Unix timestamp when the tool response was created")
    _content = param.String(default='', doc="""
        The string representation of the tool response.
        """)
    tool_responses = param.Dict(default=None, doc="""
        The tool response(s). Response from the MCP SDK
        {
            'weather_temp_mcp': {
                'mcp_name': 'weather_mcp',
                'tool_name': 'temp',
                'permission_required': False,
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
                'permission_required': True,
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

    called = param.Boolean(default=False, doc="""
        Whether the tool has been called.
        """)
    
    calling = param.Boolean(default=False, doc="""
        Whether the tool is being called.
        """)

    def __init__(self, **params):
        super().__init__(**params)
        if self.timestamp is None:
            self.timestamp = time.time()
        self.set_template()
        # self.jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader('.'))
        # self.template = self.get_template_str()
        # Keep track of watchers to clean up
        self._called_watchers = []
    
    @property
    def content(self):
        if not self._content:
            self._content = self.template.render(tool_responses=self.tool_responses)
        return self._content
    
    def set_template(self):
        # Update the template to trim whitespace and reduce extra blank lines
        self.template = jinja2.Template("""The following are responses from the tools used:
{%- for tool_name, tool_data in tool_responses.items() %}
{%- if 'response' in tool_data %}
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
{%- endif %}
{%- endfor %}""")
    
    async def call_tools(self):
        """Call all tools asynchronously and update responses. Cleans up any watchers when done."""
        self.calling = True
        # Run all tool calls concurrently
        tasks = []
        tool_keys = list(self.tool_responses.keys())
        for tool in tool_keys:
            tool_spec = self.tool_responses[tool]
            tasks.append(tool_spec['call']())
        responses = await asyncio.gather(*tasks)
        for tool, response in zip(tool_keys, responses):
            self.tool_responses[tool]['response'] = response.model_dump()
        self.called = True  # Set called first to trigger watchers
        # Clean up any watchers on 'called' if they exist
        if (called_watchers := self.param.watchers.get('called')) is not None:
            for watcher in called_watchers['value']:
                self.param.unwatch(watcher)
        self.calling = False
        return self.tool_responses
    
    async def await_ready(self):
        """Await until all tool calls have completed (called=True)."""
        # If already marked called, return immediately
        if not self.called:
            # Create a future that will be set when called becomes True
            loop = asyncio.get_event_loop()
            future = loop.create_future()
            # Watch for the 'called' flag to change
            def _on_called(event):
                if event.new:
                    # Resolve the future and unwatch
                    future.set_result(self)
                    self.param.unwatch(_watcher)
            # Register the watcher
            _watcher = self.param.watch(_on_called, 'called')
            await future
        return self

    # def get_template_str(self):

    #     if self.response_specificity == 'default':
    #         return self.jinja_env.get_template(self.response_specificity + '.jinja')

    # def render_content(self):
    #     self.content = self.template.render(self.tool_response)

    # def add_called_watcher(self, callback):
    #     """Add a watcher for the called parameter. Will be cleaned up when called is set to True."""
    #     self._called_watchers.append(callback)
    #     self.param.watch(callback, 'called')