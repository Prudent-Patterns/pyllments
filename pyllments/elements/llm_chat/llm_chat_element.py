from typing import AsyncGenerator, Generator

import param
import panel as pn
from langchain_core.messages import AIMessage

from pyllments.base.element_base import Element
from pyllments.payloads.message import MessagePayload
from pyllments.elements.llm_chat import LLMChatModel

class LLMChatElement(Element):
    model = param.ClassSelector(class_=Model)
    model_params = param.Dict(default={})
  
    def __init__(self, **params):
        super().__init__(**params)
        self.model = LLMChatModel(**self.model_params)

        self._message_output_setup()
        self._messages_input_setup()

        self._create_watchers()
        
    def _message_output_setup(self):
        if self.model.output_mode == 'stream':
            def pack(outgoing_message: AsyncGenerator | Generator) -> MessagePayload:
                payload = MessagePayload(
                    message_type='ai',
                    message_stream=outgoing_message,
                    mode='stream'
                )
                return payload
        elif self.model.output_mode == 'atomic':
            def pack(outgoing_message: AIMessage) -> MessagePayload:
                payload = MessagePayload(
                    message=outgoing_message,
                    mode='atomic'
                )
                return payload
            
        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _messages_input_setup(self):
        def unpack(payload: MessagePayload):
            if payload.model.mode == 'atomic':
                if self.model.output_mode == 'atomic':
                    self.model.outgoing_message = self.model.chat_model.invoke(
                        [payload.model.message]
                    )
                elif self.model.output_mode == 'stream':
                    self.model.outgoing_message = self.model.chat_model.stream(
                        [payload.model.message]
                    )
            elif payload.model.mode == 'batch':
                if self.model.output_mode == 'atomic':
                    self.model.outgoing_message = self.model.chat_model.invoke(
                        payload.model.messages_batch
                    )
                elif self.model.output_mode == 'stream':
                    self.model.outgoing_message = self.model.chat_model.stream(
                        payload.model.messages_batch
                    )
        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    def _create_watchers(self):
        self.model.param.watch(self._outgoing_message_updated, 'outgoing_message')
    
    @Element.port_stage_emit_if_exists('message_output', 'outgoing_message')
    def _outgoing_message_updated(self, event):
        pass