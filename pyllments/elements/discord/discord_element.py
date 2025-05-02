import asyncio
from typing import Optional

import param

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.elements.discord.discord_model import DiscordModel
from pyllments.payloads.message import MessagePayload


class DiscordElement(Element):
    """
    Discord Element enabling real-time DM interactions between the bot and users.

    This element now requires only the bot_token for configuration and uses a configurable
    criteria function to determine whether an incoming message should be processed as a DM.
    
    Model:
    - Simplified: Only bot token is needed.
    - Message handling for DM-based interactions.
    
    Ports:
    - input:
        - message_input: MessagePayload (messages to be sent to Discord)
    - output:
        - message_output: MessagePayload (messages received from Discord)
    """
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = DiscordModel(**params)
        
        self._message_output_setup()
        self._message_input_setup()
        

        
    def _message_output_setup(self):
        """Sets up the output port to forward messages received from Discord."""
        async def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message
            
        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack
        )
        
        # Watch for new messages from Discord (incoming DM).
        def _on_new_message(event):
            if event.new and event.new.model.role == "user":
                # Schedule async emission of new message payload
                self.model.loop.create_task(
                    self.ports.output['message_output'].stage_emit(new_message=event.new)
                )
                
        self.model.param.watch(_on_new_message, 'new_message', precedence=0)
        
    def _message_input_setup(self):
        """Sets up the input port for sending messages to Discord."""
        async def unpack(payload: MessagePayload):
            # Invoke the model's send_message method asynchronously.
            self.model.send_message(payload)
            
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack
        )
        
    async def cleanup(self):
        """Clean up resources when the element is no longer needed."""
        await self.model.stop()
