import param

from pyllments.base.element_base import Element
from pyllments.elements.telegram.telegram_model import TelegramModel
from pyllments.payloads.message import MessagePayload


class TelegramElement(Element):
    """
    Telegram Element enabling real-time chat interactions between the bot and users.

    This element requires app_id, api_hash, and bot_token for configuration and uses a
    configurable criteria function to determine whether an incoming message should be processed.
    
    Model:
    - Configuration: Requires app_id, api_hash, and bot_token.
    - Message handling for chat-based interactions.
    
    Ports:
    - input:
        - assistant_message_emit_input: MessagePayload (messages to be sent to Telegram)
    - output:
        - user_message_output: MessagePayload (messages received from Telegram)
        - assistant_message_output: MessagePayload (messages sent by the assistant)
        - message_output: MessagePayload        # unified port for both user and assistant messages
    """
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = TelegramModel(**params)
        
        self._user_message_output_setup()
        self._assistant_message_output_setup()
        self._assistant_message_emit_input_setup()
        
    def _user_message_output_setup(self):
        """Sets up the output port to forward user messages received from Telegram."""
        async def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message
            
        self.ports.add_output(
            name='user_message_output',
            pack_payload_callback=pack
        )
        
        # Watch for incoming user messages
        def _on_new_message(event):
            if event.new and event.new.model.role == "user":
                self.model.loop.create_task(
                    self.ports.output['user_message_output'].stage_emit(new_message=event.new)
                )
                
        self.model.param.watch(_on_new_message, 'new_message', precedence=0)
        
    def _assistant_message_output_setup(self):
        """Sets up an output port for assistant-originated MessagePayloads."""
        async def pack(assistant_message: MessagePayload) -> MessagePayload:
            return assistant_message
        self.ports.add_output(
            name='assistant_message_output',
            pack_payload_callback=pack
        )

    def _assistant_message_emit_input_setup(self):
        """Sets up an input port for assistant-originated MessagePayloads to send via Telegram."""
        async def unpack(payload: MessagePayload):
            # this call now drives both payload-resolution and the actual send
            await self.model.send_message(payload)
            # then emit downstream
            await self.ports.output['assistant_message_output'].stage_emit(assistant_message=payload)
        self.ports.add_input(
            name='assistant_message_emit_input',
            unpack_payload_callback=unpack
        )
        
    async def cleanup(self):
        """Clean up resources when the element is no longer needed."""
        await self.model.stop()
