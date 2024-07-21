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
        
        self._message_input_setup()
        self.messages_output_setup()

    def _message_input_setup(self):
        def unpack(payload: MessagePayload):
            self.model.add_message(payload.message)
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack
        )

    def _message_output_setup(self):
        def pack(self):
            return MessagePayload(message_batch=self.model.context)
        self.ports.add_output(
            name='messages_output',
            
        )

    @param.depends('model.context', watch=True)
    def view(self):
        context_view = pn.Column(
            pn.pane.Markdown("## Current Context"),
            *[pn.pane.Markdown(msg.message.content) for msg in self.model.context]
        )
        return context_view