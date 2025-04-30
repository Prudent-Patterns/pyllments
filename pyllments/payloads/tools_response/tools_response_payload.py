import panel as pn
from jinja2 import Template
from loguru import logger
from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload
from pyllments.common.loop_registry import LoopRegistry

from .tools_response_model import ToolsResponseModel


class ToolsResponsePayload(Payload):
    """
    A payload containing tool responses from one or many tool calls.
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
        self.model = ToolsResponseModel(**params)

    @Component.view
    def create_tool_response_view(
        self,
        card_css: list = [],
        str_css: list = [],
        parameters_css: list = [],
        response_md_css: list = []
    ):
        # Create a placeholder column that will be updated dynamically
        # max-height: none is NEEDED to avoid weird placement in columns
        placeholder = pn.Column(pn.pane.Str('Loading tool responses...'), styles={'flex': '0 0 auto', 'height': 'fit-content', 'max-height': 'none'})
        
        # Build permission states: 'pending' for tools that require approval, else 'auto'
        states: dict[str, str] = {
            name: 'pending' if data.get('permission_required', False) else 'auto'
            for name, data in self.model.tool_responses.items()
        }

        # track which names we've already kicked off
        scheduled: set[str] = set()

        # Async helper to call a single tool and re-render
        async def _run_tool(tool_name: str):
            # remember we already ran it
            scheduled.add(tool_name)
            tool_data = self.model.tool_responses[tool_name]
            response = await tool_data['call']()
            tool_data['response'] = response.model_dump()
            LoopRegistry.get_loop().create_task(update_view())

        # Main update logic: render prompts or results based on state
        async def update_view():
            placeholder.clear()
            tool_cards = []
            for tool_name, tool_data in self.model.tool_responses.items():
                state = states.get(tool_name, 'auto')
                # Skip denied
                if state == 'denied':
                    continue

                # Prompt for pending tools
                if state == 'pending':
                    approve = pn.widgets.Button(name='Approve', button_type='primary',
                                                stylesheets=[":host(.solid) .bk-btn.bk-btn-primary {background-color: var(--tertiary-accent-color); font-size: 15px}",
                                                             ".bk-btn, ::file-selector-button {padding: 0px 10px}"])
                    deny = pn.widgets.Button(name='Deny', button_type='danger',
                                             stylesheets=[":host(.solid) .bk-btn.bk-btn-danger {background-color: var(--primary-accent-color); font-size: 15px}",
                                                          ".bk-btn, ::file-selector-button {padding: 0px 10px}"])

                    def on_approve(evt, tool_name=tool_name):
                        states[tool_name] = 'approved'
                        LoopRegistry.get_loop().create_task(_run_tool(tool_name))

                    def on_deny(evt, tool_name=tool_name):
                        states[tool_name] = 'denied'
                        LoopRegistry.get_loop().create_task(update_view())

                    approve.on_click(on_approve)
                    deny.on_click(on_deny)
                    # Construct styled header for pending state
                    header = pn.Row(
                        pn.pane.Str(tool_data['mcp_name'], stylesheets=str_css),
                        pn.pane.Str(' is requesting to run ', styles={'font-size': '14px'}),
                        pn.pane.Str(tool_data['tool_name'], stylesheets=str_css)
                    )
                    tool_cards.append(
                        pn.layout.Card(
                            header=header,
                            objects=[pn.Row(approve, deny)],
                            stylesheets=card_css
                        )
                    )
                    continue

                # Auto or approved: parameters + response/processing
                tool_card_kwargs = {'collapsed': False, 'objects': []}
                if tool_data.get('parameters'):
                    md = self.parameters_template.render(parameters=tool_data['parameters'])
                    tool_card_kwargs['objects'].append(pn.pane.Markdown(md, stylesheets=parameters_css))
                else:
                    tool_card_kwargs['objects'].append(pn.pane.Markdown('No parameters provided.', stylesheets=parameters_css))

                # Construct styled header for completed state
                header = pn.Row(
                    pn.pane.Str(tool_data['mcp_name'], stylesheets=str_css),
                    pn.pane.Str(' has run ', styles={'font-size': '14px'}),
                    pn.pane.Str(tool_data['tool_name'], stylesheets=str_css)
                )
                if 'response' in tool_data and tool_data['response'].get('content'):
                    text = tool_data['response']['content'][0]['text']
                    pane = pn.pane.Str(text, stylesheets=response_md_css)
                else:
                    # only schedule if:
                    #  1) we haven't already run it, and
                    #  2) it has no 'response' yet
                    if state in ('auto','approved') \
                            and tool_name not in scheduled \
                            and 'response' not in tool_data:
                        LoopRegistry.get_loop().create_task(_run_tool(tool_name))
                    pane = pn.pane.Str('Processing...', stylesheets=response_md_css)

                tool_card_kwargs['objects'].append(pn.Column(pn.pane.Str('Response:',
                                                                         stylesheets=[":host {margin-bottom: 0px}"]), pane))
                tool_cards.append(
                    pn.layout.Card(header=header, **tool_card_kwargs, stylesheets=card_css)
                )

            placeholder.extend(tool_cards)
            # Once no tools remain pending approval, signal that the payload is fully processed
            if not any(state == 'pending' for state in states.values()):
                # Mark model.called to trigger watchers
                self.model.called = True

        # Initial render
        LoopRegistry.get_loop().create_task(update_view())
        
        return placeholder
    
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
    
