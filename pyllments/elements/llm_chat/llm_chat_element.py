from typing import Union

from pyllments.base.element_base import Element
from pyllments.payloads.message import MessagePayload
from pyllments.elements.llm_chat import LLMChatModel

class LLMChatElement(Element):
    """Responsible for using LLMs to respond to messages and sets of messages"""
    def __init__(self, **params):
        super().__init__(**params)

        self.model = LLMChatModel(**params)
        self._message_output_setup()
        self._messages_input_setup()
        
    def _message_output_setup(self):
        def pack(message_payload: MessagePayload) -> MessagePayload:
            return message_payload
            
        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _messages_input_setup(self):
        def unpack(payload: Union[list[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            response = self.model.generate_response(payloads)
            self.ports.output['message_output'].stage_emit(message_payload=response)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)