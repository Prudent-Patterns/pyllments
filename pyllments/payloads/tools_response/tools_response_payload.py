import panel as pn
from jinja2 import Template

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload

from .tools_response_model import ToolsResponseModel

from loguru import logger

class ToolsResponsePayload(Payload):
    """
    A payload containing tool responses from one or many tool calls.
    """

    parameters_template = Template("""```javascript
{
{% for key, value in parameters.items() %}
{{ key }}: {{ value }}
{% endfor %}
}
```""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolsResponseModel(**params)

    @Component.view
    def create_tool_response_view(self):
        tool_cards = []
        logger.info(f"Creating tool response view for {self.model.tool_responses}")
        for tool_name, tool_data in self.model.tool_responses.items():
            tool_card_kwargs = {'collapsed': True}
            if tool_data.get('parameters', None):
                tool_card_kwargs['collapsible'] = True
                parameters_str = self.parameters_template.render(parameters=tool_data['parameters'])
                tool_card_kwargs['objects'] = [pn.pane.Markdown(parameters_str)]
            else:
                tool_card_kwargs['collapsible'] = False
            card_title = f"{tool_data['mcp_name']} is running {tool_data['tool_name']}"
            tool_card = pn.layout.Card(title=card_title, **tool_card_kwargs)
            tool_cards.append(tool_card)

        return pn.Column(*tool_cards)
    
