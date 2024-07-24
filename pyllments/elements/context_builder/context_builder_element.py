from collections import deque
from typing import List

import param
import panel as pn

from pyllments.base.component_base import Component
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
        - messages_output: List[MessagePayload]
    """
    context_view = param.ClassSelector(class_=pn.Column)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ContextBuilderModel()
        
        self._message_input_setup()
        self._messages_output_setup()

    def _message_input_setup(self):
        def unpack(payload: MessagePayload):
            self.model.load_message(payload.model.message)

        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack
        )

    def _messages_output_setup(self):
        def pack(context: deque) -> List[MessagePayload]:
            message_list = list(context)
            return message_list
        
        self.ports.add_output(
            name='messages_output',
            pack_payload_callback=pack
        )

    def create_context_view(self):
        pass

    def _create_watchers(self):
        self.model.param.watch(self.context_change_callback, 'context')

    @Element.port_stage_emit_if_exists('messages_output', 'context')
    def context_change_callback(self):
        pass

    def create_context_view(self):
        if self._view_exists(self.context_view):
            return self.context_view
        self.context_view = pn.Column(
            pn.pane.Markdown("## Current Context"),
            *[pn.pane.Markdown(msg.message.content) for msg in self.model.context]
        )
        def _update_chatfeed(self, event):
            self.context_view.objects = [
                pn.pane.Markdown(msg.message.content) for msg in self.model.context
            ]
        self.model.param.watch(_update_chatfeed, 'context')
        
        return self.context_view
