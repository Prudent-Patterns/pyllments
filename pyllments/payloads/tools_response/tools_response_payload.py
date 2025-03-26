import panel as pn
from jinja2 import Template

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload

from .tools_response_model import ToolsResponseModel


class ToolsResponsePayload(Payload):
    """
    A payload containing tool responses from one or many tool calls.
    """

    parameters_template = Template("""```javascript
{
{% for key, value in parameters.items() -%}
{{ key }}: {{ value }}{% if not loop.last %},{% endif %}
{%- endfor %}
}
```""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolsResponseModel(**params)

    @Component.view
    def create_tool_response_view(
        self,
        card_css: list = [],
        str_css: list = [],
        parameters_css: list = [],
        response_md_css: list = []
    ):
        tool_cards = []
        for tool_name, tool_data in self.model.tool_responses.items():
            tool_card_kwargs = {'collapsed': False}
            tool_card_kwargs['objects'] = []
            if tool_data.get('parameters', None):
                parameters_str = self.parameters_template.render(parameters=tool_data['parameters'])
                tool_card_kwargs['objects'].append(pn.pane.Markdown(
                    parameters_str,
                    # styles={'margin': '-9px 0px'},
                    stylesheets=parameters_css
                    )
                )
            card_header_row = pn.Row(
                pn.pane.Str(tool_data['mcp_name'], stylesheets=str_css),
                pn.pane.Str('is running', styles={'font-size': '14px'}),
                pn.pane.Str(tool_data['tool_name'], stylesheets=str_css)
            )
            response_indicator = pn.pane.Str('Response:', stylesheets=str_css, styles={'margin-left': '0px'})
            response_str = pn.pane.Str(tool_data['response']['content'][0]['text'],
                                       stylesheets=response_md_css)

            response_col = pn.Column(response_indicator, response_str)
            tool_card_kwargs['objects'].append(response_col)
            
            tool_card = pn.layout.Card(
                header=card_header_row,
                **tool_card_kwargs,
                stylesheets=card_css
                )
            tool_cards.append(tool_card)

        return pn.Column(*tool_cards, styles={
            'flex': '0 0 auto',
            'height': 'fit-content',
            'max-height': 'none',
            'overflow': 'auto'
            })
    
    @Component.view
    def create_collapsible_view(
        self,
        card_css: list = [],
        str_css: list = [],
        parameters_css: list = [],
        response_md_css: list = []
    ):
        """Creates a collapsible view of the tool response for use in history."""
        return self.create_tool_response_view(
            card_css=card_css,
            str_css=str_css,
            parameters_css=parameters_css,
            response_md_css=response_md_css
        )
    
