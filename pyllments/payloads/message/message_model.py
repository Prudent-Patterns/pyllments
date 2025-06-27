import asyncio
import time

from loguru import logger
import param

from pyllments.base.model_base import Model
from pyllments.runtime.loop_registry import LoopRegistry
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

    loop = param.Parameter(default=None, doc="Asyncio event loop associated with this message model")

    def __init__(self, **params):
        super().__init__(**params)
        if params.get('loop', None) is None:
            params['loop'] = LoopRegistry.get_loop()
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
        
    async def await_ready(self):
        """
        Passively await until the message is fully processed (streamed or coroutine resolved) without triggering the process.
        Returns the model instance for chaining.
        """
        if self.mode == 'atomic' and self.message_coroutine is not None:
            # Create a future to wait for coroutine resolution
            future = self.loop.create_future()
            def on_resolved(event):
                if event.new is None:  # Coroutine has been resolved
                    future.set_result(self)
                    self.param.unwatch(watcher)
            watcher = self.param.watch(on_resolved, 'message_coroutine')
            await future
        elif self.mode == 'stream' and not self.streamed:
            # Create a future to wait for streaming completion
            future = self.loop.create_future()
            def on_streamed(event):
                if event.new:  # Streaming is complete
                    future.set_result(self)
                    self.param.unwatch(watcher)
            watcher = self.param.watch(on_streamed, 'streamed')
            await future
        return self



