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
        - assistant_message_emit_input: MessagePayload (messages to be sent to Discord)
    - output:
        - user_message_output: MessagePayload (messages received from Discord)
        - assistant_message_output: MessagePayload (messages received from Discord)
        - message_output: MessagePayload        # unified port for both user and assistant messages
    """
    
    def __init__(self, **params):
        super().__init__(**params)
        self.model = DiscordModel(**params)
        
        self._user_message_output_setup()
        self._assistant_message_output_setup()
        self._message_output_setup()
        self._assistant_message_emit_input_setup()
        
    def _user_message_output_setup(self):
        """Sets up the output port to forward user messages received from Discord."""
        async def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message
            
        self.ports.add_output(
            name='user_message_output',
            pack_payload_callback=pack
        )
        
        # Also add unified message output
        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack
        )
        
        # Watch for new messages from Discord (incoming DM).
        def _on_new_message(event):
            if event.new and event.new.model.role == "user":
                # Emit to both user_message_output and unified message_output
                self.model.loop.create_task(
                    self.ports.output['user_message_output'].stage_emit(new_message=event.new)
                )
                self.model.loop.create_task(
                    self.ports.output['message_output'].stage_emit(new_message=event.new)
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
        """Sets up an input port for assistant-originated MessagePayloads to send via Discord."""
        async def unpack(payload: MessagePayload):
            # Send the assistant message (awaits content resolution internally)
            await self.model.send_message(payload)
            # Emit after sending
            await self.ports.output['assistant_message_output'].stage_emit(assistant_message=payload)
            # Also emit on unified message_output
            await self.ports.output['message_output'].stage_emit(assistant_message=payload)

        self.ports.add_input(
            name='assistant_message_emit_input',
            unpack_payload_callback=unpack
        )
        
    def _message_output_setup(self):
        """Sets up a unified output port for user and assistant MessagePayloads."""
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload
        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack
        )
        
    async def cleanup(self):
        """Clean up resources when the element is no longer needed."""
        await self.model.stop()
