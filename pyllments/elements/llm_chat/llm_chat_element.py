from typing import AsyncGenerator, Generator

import param
import panel as pn
from langchain_core.messages import AIMessage

from pyllments.base.element_base import Element
from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.elements.llm_chat import LLMChatModel


class LLMChatElement(Element):
  
    def __init__(
            self, chat_model=None, provider_name='openai',
            model_name='gpt-4o-mini', model_args={}, output_mode='stream', **params):
        super().__init__(**params)
        
        self.model = LLMChatModel(
            chat_model=chat_model, provider_name=provider_name, model_name=model_name,
            model_args=model_args, output_mode=output_mode)
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