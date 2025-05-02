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
        - message_input: MessagePayload (messages to be sent to Telegram)
    - output:
        - message_output: MessagePayload (messages received from Telegram)
    """
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = TelegramModel(**params)
        
        self._message_output_setup()
        self._message_input_setup()
        
    def _message_output_setup(self):
        """Sets up the output port to forward messages received from Telegram."""
        async def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message
            
        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack
        )
        
        # Watch for new messages from Telegram (incoming messages)
        def _on_new_message(event):
            if event.new and event.new.model.role == "user":
                # Schedule async emission of the new Telegram message payload
                self.model.loop.create_task(
                    self.ports.output['message_output'].stage_emit(new_message=event.new)
                )
                
        self.model.param.watch(_on_new_message, 'new_message', precedence=0)
        
    def _message_input_setup(self):
        """Sets up the input port for sending messages to Telegram."""
        async def unpack(payload: MessagePayload):
            # Invoke the model's send_message method asynchronously
            self.model.send_message(payload)
            
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack
        )
        
    async def cleanup(self):
        """Clean up resources when the element is no longer needed."""
        await self.model.stop()
