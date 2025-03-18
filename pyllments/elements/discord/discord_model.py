import os
from typing import Callable

import discord
import param
from loguru import logger

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.common.loop_registry import LoopRegistry


class DiscordModel(Model):
    """
    Model for handling Discord client initialization and message handling.
    
    This simplified model only requires the bot token for authentication.
    It uses a configurable criteria function to determine whether an incoming message
    should be processed as a DM. The default criteria checks if the message channel is a DM.

    Parameters
    ----------
    bot_token : str
        Discord bot token for authentication.
    on_message_criteria : Callable, optional
        A function that receives a discord.Message and returns a boolean indicating
        if the message meets the criteria (default: checks if channel is DM).
    """
    # Configuration parameters
    bot_token = param.String(doc="Discord bot token for authentication")
    on_message_criteria = param.Callable(
        default=lambda message: isinstance(message.channel, discord.DMChannel),
        doc="Function to determine if an incoming message meets criteria for processing as a DM"
    )
    
    # Runtime parameters
    is_ready = param.Boolean(default=False, doc="Indicates if the Discord client is ready")
    new_message = param.ClassSelector(class_=MessagePayload, doc="Latest message received from Discord")
    
    loop = param.Parameter(default=None, doc="The event loop to use for asynchronous operations")
    
    def __init__(self, **params):
        super().__init__(**params)
        
        # Obtain the event loop using the registry.
        # This will fetch the currently running loop (e.g., uviCorn's loop)
        # if available or create a new one if none is running.
        if not self.loop:
            self.loop = LoopRegistry.get_loop()
        
        # Initialize Discord client with appropriate intents.
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        
        self.client = discord.Client(intents=intents)
        self._last_dm_channel = None  # Stores the DM channel of the last valid message.
        self._setup_discord_events()
        
        if not self.bot_token:
            self.bot_token = os.getenv('DISCORD_BOT_TOKEN')
        
        # Automatically schedule the Discord client's start routine.
        # This ensures the scheduling happens in the model.
        self.loop.create_task(self.start())
        
    def _setup_discord_events(self):
        """Set up Discord client event handlers."""
        
        @self.client.event
        async def on_ready():
            """Called when the bot has successfully connected to Discord."""
            logger.info(f"Discord bot {self.client.user} is ready")
            self.is_ready = True

        @self.client.event
        async def on_message(message):
            """Called when a message is received."""
            # Ignore messages from the bot itself.
            if message.author == self.client.user:
                return
                
            # Process message if it meets the criteria.
            if self.on_message_criteria(message):
                self._last_dm_channel = message.channel
                self.new_message = MessagePayload(
                    role="user",
                    content=message.content,
                    mode="atomic"
                )
                
    def send_message(self, payload: MessagePayload):
        """
        Schedules sending a message via the last DM channel using the cached event loop.
        
        This method is intended to be called by the Discord Element when it wants to
        dispatch an outgoing message from the bot.
        """
        if not self.is_ready or not self._last_dm_channel:
            logger.warning("Discord client not ready or no DM channel available")
            return
        
        # Ensure that only messages from valid roles are sent.
        if payload.model.role not in ["assistant", "system"]:
            logger.info("Message role not valid for sending via Discord DM: ignoring")
            return
        
        # Schedule the asynchronous send operation using the cached event loop.
        self.loop.create_task(self._async_send_message(payload))
        
    async def _async_send_message(self, payload: MessagePayload):
        """
        Internal asynchronous method that sends the message via the last DM channel.
        """
        try:
            message = await payload.model.aget_message()
            await self._last_dm_channel.send(message)
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
    
    async def start(self):
        """Start the Discord client."""
        if not self.bot_token:
            raise ValueError("Bot token not provided")
            
        try:
            await self.client.start(self.bot_token)
        except Exception as e:
            logger.error(f"Error starting Discord client: {str(e)}")
            raise

    async def stop(self):
        """Stop the Discord client and reset runtime state."""
        if self.client:
            await self.client.close()
            self.is_ready = False
            self._last_dm_channel = None
