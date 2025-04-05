import asyncio
import time

from loguru import logger
import param

from pyllments.base.model_base import Model
from pyllments.common.loop_registry import LoopRegistry
# from pyllments.common.tokenizers import get_token_len


class MessageModel(Model):
    """
    Model representing a message. Handles both atomic and streaming scenarios.
    In streaming mode, this model will trigger the message stream when a message is requested.
    In atomic mode, it now takes into account the stored coroutine and awaits it (or executes it synchronously)
    to populate the message content.
    """
    role = param.Selector(
        default='user', 
        objects=['system', 'assistant', 'user', 'function', 'tool', 'developer'],
        doc="Message role - matches OpenAI/LiteLLM format"
    )
    
    content = param.String(default='', doc="Message content")
    
    mode = param.Selector(
        objects=['atomic', 'stream'],
        default='atomic',
        doc="Determines whether the message is captured atomically or via streaming"
    )
    
    message_coroutine = param.Parameter(
        default=None,
        doc="Used with stream mode for assistant messages or atomic mode when a coroutine needs to be awaited"
    )
    
    streamed = param.Boolean(default=False, doc="Indicates whether the message has been fully streamed")
        
    embedding = param.Parameter(doc="Message embedding if generated")

    timestamp = param.Number(default=None, doc="Unix timestamp when the message was created")

    def __init__(self, **params):
        super().__init__(**params)
        self.timestamp = time.time() if not self.timestamp else self.timestamp

        # Used to ensure only one streaming task is started for stream messages.
        self._stream_task = None

    async def stream(self):
        """
        Processes the streaming message. Asynchronously iterates over the message stream, 
        updating the content (in chunks) and ultimately marks the message as streamed.
        """
        if self.mode != 'stream':
            raise ValueError("Cannot stream: Mode is not set to 'stream'")
            
        self.content = ''
        buffer = ''
        
        # Trigger the external coroutine that yields the message stream.
        message_stream = await self.message_coroutine
        async for chunk in message_stream:
            delta = chunk['choices'][0].get('delta', {}).get('content', '')
            if delta:
                buffer += delta
                # Flush the buffer if it's large enough or contains a newline.
                if len(buffer) >= 10 or '\n' in buffer:  
                    self.content += buffer
                    buffer = ''
        
        # Append any last remaining content.
        if buffer:
            self.content += buffer
                
        logger.info("Completed message stream")
        self.streamed = True

        # Clean up any watchers on 'streamed' if they exist.
        if (streamed_watchers := self.param.watchers.get('streamed')) is not None:
            for watcher in streamed_watchers['value']:
                self.param.unwatch(watcher)

    # def get_token_len(self, model=None, push_stream=False):
    #     if model in self.tokenization_map:
    #         return self.tokenization_map[model]
    #     match self.mode:
    #         case 'atomic':
    #             token_length = get_token_len(self.message.content, model)
    #         case 'stream':
    #             if push_stream:
    #                 self.stream() 
    #             if self.streamed:
    #                 token_length = get_token_len(self.message.content, model)
    #             else:
    #                 raise ValueError("Message has not been streamed")
    #         case _:
    #             raise ValueError("Invalid mode: must be 'atomic' or 'stream'")
        
    #     self.tokenization_map[model] = token_length
    #     return token_length

    async def aget_message(self) -> str:
        """
        Asynchronously retrieves the complete message content.
        If streaming is required and not yet complete or if this is an atomic response with a coroutine,
        the corresponding process is initiated and awaited.

        Returns
        -------
        str
            The complete message content.
        """
        if self.mode == 'atomic':
            if self.message_coroutine is not None:
                # Await the stored atomic coroutine and extract message content from ModelResponse
                response = await self.message_coroutine
                self.content = response['choices'][0]['message']['content']
                self.message_coroutine = None
            return self.content
        elif self.mode == 'stream':
            if not self.streamed:
                # If the streaming task hasn't started, initiate it.
                if self._stream_task is None:
                    self._stream_task = asyncio.create_task(self.stream())
                # Wait for the streaming to complete.
                await self._stream_task
            return self.content
        else:
            raise ValueError(f"Unsupported mode: {self.mode}")

    # TODO: CONFIRM REMOVAL -- CAUSES DEADLOCKS WHEN THERE IS A RUNNING LOOP
    # NO BUENO
    # def get_message(self) -> str:
    #     """
    #     Synchronously retrieves the complete message content.
    #     For stream mode, if the message hasn't been fully streamed,
    #     this method will block until the stream is complete.
    #     For atomic mode, if there is a stored coroutine, it will be executed synchronously.

    #     Returns
    #     -------
    #     str
    #         The complete message content.

    #     Raises
    #     ------
    #     RuntimeError
    #         If called in an active asynchronous event loop.
    #     """
    #     loop = LoopRegistry.get_loop()
    #     if self.mode == 'atomic':
    #         if self.message_coroutine is not None:
    #             if loop.is_running():
    #                 # Use run_coroutine_threadsafe to get the result without disturbing the running Panel loop
    #                 response = asyncio.run_coroutine_threadsafe(self.message_coroutine, loop).result()
    #             else:
    #                 response = loop.run_until_complete(self.message_coroutine)
    #             self.content = response['choices'][0]['message']['content']
    #             self.message_coroutine = None
    #         return self.content
    #     elif self.mode == 'stream':
    #         if loop.is_running():
    #             return asyncio.run_coroutine_threadsafe(self.aget_message(), loop).result()
    #         else:
    #             return loop.run_until_complete(self.aget_message())
    #     else:
    #         raise ValueError(f"Unsupported mode: {self.mode}")
        



