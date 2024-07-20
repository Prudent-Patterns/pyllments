import param
import panel as pn

from pyllments.base.element_base import Element
from pyllments.payloads.message.message_payload import MessagePayload
from .context_builder_model import ContextBuilderModel

class ContextBuilderElement(Element):
    """
    Responsible for building the context that is sent to the LLM
    Model:
    - history responsible for building context
    - new message
    - context
    Views:
    - current context column
    Ports:
    - input:
        - message_input: MessagePayload
    - output:
        - messages_output: MessagePayload
    """

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ContextBuilderModel()
        
        self.input_ports['message_input'] = self.message_input
        self.output_ports['messages_output'] = self.messages_output

    def message_input(self, payload: MessagePayload):
        context = self.model.add_message(payload.model)
        self.messages_output(MessagePayload(message_batch=context))

    def messages_output(self, payload: MessagePayload):
        self.trigger('messages_output', payload)

    @param.depends('model.context', watch=True)
    def view(self):
        context_view = pn.Column(
            pn.pane.Markdown("## Current Context"),
            *[pn.pane.Markdown(msg.message.content) for msg in self.model.context]
        )
        return context_view