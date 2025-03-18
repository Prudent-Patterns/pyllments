import os
from typing import Optional, Union

import param
from loguru import logger
from telethon import TelegramClient, events

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.common.loop_registry import LoopRegistry


class TelegramModel(Model):
    """
    Model for handling Telegram client initialization and message handling using Telethon.
    
    This model requires app_id, api_hash, and bot_token for authentication.
    It uses a configurable criteria function to determine whether an incoming message
    should be processed. The default criteria processes all private messages.
    """
    # Configuration parameters
    app_id = param.String(default=None, doc="Telegram application ID")
    api_hash = param.String(default=None, doc="Telegram API hash")
    bot_token = param.String(default=None, doc="Telegram bot token for authentication")
    start_message_with = param.Parameter(default=None, allow_None=True, doc="""
        Telegram chat ID or username to message upon startup""")
    on_message_criteria = param.Callable(default=lambda message: message.is_private, doc="""
        Function to determine if an incoming message meets criteria for processing""")
    # Runtime parameters
    is_ready = param.Boolean(default=False, doc="Indicates if the Telegram client is ready")
    new_message = param.ClassSelector(class_=MessagePayload, doc="Latest message received from Telegram")
    
    loop = param.Parameter(default=None, doc="The event loop to use for asynchronous operations")
    def __init__(self, **params):
        super().__init__(**params)
        
        # Obtain the event loop using the registry
        if not self.loop:
            self.loop = LoopRegistry.get_loop()
        
        # Load environment variables if not provided
        if not self.app_id:
            self.app_id = os.getenv('TELEGRAM_APP_ID')
        if not self.api_hash:
            self.api_hash = os.getenv('TELEGRAM_API_HASH')
        if not self.bot_token:
            self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            
        # Initialize Telegram client
        self.client = TelegramClient(
            'bot_session',
            int(self.app_id),
            self.api_hash,
            loop=self.loop
        ).start(bot_token=self.bot_token)
        
        self._last_chat = None  # Stores the chat of the last valid message
        self._setup_telegram_events()
        
        # Schedule the Telegram client's start routine
        self.loop.create_task(self.start())
        
    def _setup_telegram_events(self):
        """Set up Telegram client event handlers."""
        
        @self.client.on(events.NewMessage)
        async def on_message(event):
            """Called when a message is received."""
            # Ignore messages from the bot itself
            if event.message.out:
                return
                
            # Process message if it meets the criteria
            if self.on_message_criteria(event.message):
                self._last_chat = await event.get_chat()
                self.new_message = MessagePayload(
                    role="user",
                    content=event.message.text,
                    mode="atomic"
                )
                
    async def _resolve_chat_id(self, target: Union[int, str]) -> Optional[int]:
        """
        Resolves a target (username or chat ID) to a chat ID.
        
        Parameters
        ----------
        target : Union[int, str]
            The target to resolve. Can be either a chat ID (int) or username (str).
            
        Returns
        -------
        Optional[int]
            The resolved chat ID if found, None otherwise.
        """
        if isinstance(target, int):
            return target
            
        # If it's a username, try to find it in dialogs
        if isinstance(target, str):
            try:
                # Remove @ if present
                username = target.lstrip('@')
                async for dialog in self.client.iter_dialogs():
                    if dialog.entity.username and dialog.entity.username.lower() == username.lower():
                        return dialog.id
                logger.warning(f"Could not find chat ID for username {target}")
            except Exception as e:
                logger.error(f"Error resolving username {target}: {str(e)}")
        return None
                
    def send_message(self, payload: MessagePayload):
        """
        Schedules sending a message via the last chat using the cached event loop.
        
        This method is intended to be called by the Telegram Element when it wants to
        dispatch an outgoing message from the bot.
        """
        if not self.is_ready:
            logger.warning("Telegram client not ready")
            return
            
        if not self._last_chat and not isinstance(payload, tuple):
            logger.warning("No chat available and no target specified")
            return
        
        # Ensure that only messages from valid roles are sent
        if payload.model.role not in ["assistant", "system"]:
            logger.info("Message role not valid for sending via Telegram: ignoring")
            return
        
        # Schedule the asynchronous send operation using the cached event loop
        self.loop.create_task(self._async_send_message(payload))
        
    async def _async_send_message(self, payload: MessagePayload, target: Optional[Union[int, str]] = None):
        """
        Internal asynchronous method that sends the message via the last chat or specified target.
        
        Parameters
        ----------
        payload : MessagePayload
            The message payload to send
        target : Optional[Union[int, str]]
            Optional target to send message to. Can be a chat ID (int) or username (str).
            If None, uses the last chat.
        """
        try:
            message = await payload.model.aget_message()
            
            if target:
                chat_id = await self._resolve_chat_id(target)
                if chat_id:
                    await self.client.send_message(chat_id, message)
                else:
                    logger.error(f"Could not resolve chat ID for target {target}")
            else:
                await self.client.send_message(self._last_chat, message)
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
    
    async def start(self):
        """Start the Telegram client and optionally send initial message."""
        if not all([self.app_id, self.api_hash, self.bot_token]):
            raise ValueError("Missing required Telegram credentials")
            
        try:
            # Connect and sign in
            await self.client.connect()
            self.is_ready = True
            logger.info("Telegram bot is ready")
            
            # Send initial message if start_message_with is set
            if self.start_message_with:
                try:
                    chat_id = await self._resolve_chat_id(self.start_message_with)
                    if chat_id:
                        initial_message = MessagePayload(
                            role="assistant",
                            content="Hello! I'm your bot assistant. How can I help you today?",
                            mode="atomic"
                        )
                        await self._async_send_message(initial_message, chat_id)
                        logger.info(f"Sent initial message to chat ID {chat_id}")
                    else:
                        logger.warning(
                            f"Could not send initial message: Unable to resolve chat ID for {self.start_message_with}. "
                            "Note: Bots can only message users who have previously interacted with them."
                        )
                except Exception as e:
                    logger.error(f"Failed to send initial message: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error starting Telegram client: {str(e)}")
            raise

    async def stop(self):
        """Stop the Telegram client and reset runtime state."""
        if self.client:
            await self.client.disconnect()
            self.is_ready = False
            self._last_chat = None
