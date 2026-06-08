from __future__ import annotations

from typing import TYPE_CHECKING

from jinja2 import Template

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload

from .tool_use_model import ToolUseModel

if TYPE_CHECKING:
    import panel as pn


class ToolUsePayload(Payload):
    """
    Durable payload representing one or more tool calls across their lifecycle.
    """

    parameters_template = Template("""```
{
{%- for key, value in parameters.items() %}
{{ key }}: {{ value }}{% if not loop.last %},{% endif %}
{%- endfor %}
}
```""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolUseModel(**params)

    @Component.view
    def create_tool_use_view(
        self,
        card_css: list | None = None,
        str_css: list | None = None,
        parameters_css: list | None = None,
        response_md_css: list | None = None,
    ) -> pn.Column:
        """Render tool-use records by lifecycle status; execution stays in ToolUseElement."""
        import panel as pn

        card_css = card_css or []
        str_css = str_css or []
        parameters_css = parameters_css or []
        response_md_css = response_md_css or []

        # Header verb reflects where the record is in its lifecycle.
        status_verbs = {
            'awaiting_permission': ' is requesting to run ',
            'approved': ' is approved to run ',
            'running': ' is running ',
            'denied': ' was denied running ',
            'failed': ' failed running ',
        }

        cards = []
        for record in self.model.tool_uses.values():
            provider = record.get('provider_name') or record.get('adapter_name', '')
            tool_label = record.get('tool_name') or record.get('model_tool_name', '')
            status = record.get('status', 'pending')

            header = pn.Row(
                pn.pane.Str(provider, stylesheets=str_css),
                pn.pane.Str(status_verbs.get(status, ' has run '), styles={'font-size': '14px'}),
                pn.pane.Str(tool_label, stylesheets=str_css),
            )

            objects = []
            params = record.get('parameters') or {}
            if params:
                md = self.parameters_template.render(parameters=params)
                objects.append(pn.pane.Markdown(md, stylesheets=parameters_css))
            else:
                objects.append(pn.pane.Markdown('No parameters provided.', stylesheets=parameters_css))

            result = record.get('result')
            error = record.get('error')
            if result and result.get('content'):
                text = '\n'.join(
                    item.get('text', '')
                    for item in result['content']
                    if item.get('type') == 'text'
                )
                objects.append(
                    pn.Column(
                        pn.pane.Str('Response:', stylesheets=[":host {margin-bottom: 0px}"]),
                        pn.pane.Str(text, stylesheets=response_md_css),
                    )
                )
            elif error:
                objects.append(
                    pn.pane.Str(error.get('message', 'Tool failed'), stylesheets=response_md_css)
                )
            elif status == 'denied':
                reason = (record.get('permission') or {}).get('reason')
                objects.append(
                    pn.pane.Str(
                        f"Denied{': ' + reason if reason else ''}",
                        stylesheets=response_md_css,
                    )
                )
            else:
                objects.append(pn.pane.Str('Processing...', stylesheets=response_md_css))

            cards.append(
                pn.layout.Card(header=header, objects=objects, collapsed=False, stylesheets=card_css)
            )

        return pn.Column(*cards, styles={'flex': '0 0 auto', 'height': 'fit-content'})

    @Component.view
    def create_collapsible_view(
        self,
        card_css: list | None = None,
        str_css: list | None = None,
        parameters_css: list | None = None,
        response_md_css: list | None = None,
    ) -> pn.Column:
        """Collapsible view for history; delegates to the main tool-use view."""
        return self.create_tool_use_view(
            card_css=card_css,
            str_css=str_css,
            parameters_css=parameters_css,
            response_md_css=response_md_css,
        )
