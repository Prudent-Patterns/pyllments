import asyncio

from loguru import logger
import param

from pyllments.base.model_base import Model
# from pyllments.common.tokenizers import get_token_len


class MessageModel(Model):
    role = param.Selector(
        default='user', 
        objects=['system', 'assistant', 'user', 'function', 'tool', 'developer'],
        doc="Message role - matches OpenAI/LiteLLM format")
    
    content = param.String(default='', doc="Message content")
    
    mode = param.Selector(
        objects=['atomic', 'stream'],
        default='atomic')
    
    message_coroutine = param.Parameter(doc="""
        Used with stream mode for assistant messages""")
    
    streamed = param.Boolean(default=False, doc="""
        Used to identify if the message has been streamed""")
        
    embedding = param.Parameter(doc="""
        Message embedding if generated""")

    def __init__(self, **params):
        super().__init__(**params)

    async def stream(self):
        if self.mode != 'stream':
            raise ValueError("Cannot stream: Mode is not set to 'stream'")
            
        self.content = ''
        # Buffer to store the streamed content and help not overwhelm redraws in the UI
        buffer = ''
        
        message_stream = await self.message_coroutine
        async for chunk in message_stream:
            delta = chunk['choices'][0].get('delta', {}).get('content', '')
            if delta:
                buffer += delta
                # Only update content and trigger redraws every N characters or on certain conditions
                if len(buffer) >= 10 or '\n' in buffer:  
                    self.content += buffer
                    buffer = ''
        
        # Flush any remaining content in the buffer
        if buffer:
            self.content += buffer
                
        logger.info("Completed message stream")
        self.streamed = True
        # Remove watchers that may have been using streamed
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

    async def streamed_message(self) -> str:
        """Wait for streaming to complete and return the final message content.
        
        Returns
        -------
        str
            The complete message content after streaming
        """
        if self.mode != 'stream':
            return self.content
            
        if self.streamed:
            return self.content
            
        done_future = asyncio.Future()
        
        def on_streamed_change(event):
            if event.new and not done_future.done():
                done_future.set_result(self.content)
        
        watcher = self.param.watch(on_streamed_change, 'streamed')
        try:
            return await done_future
        finally:
            self.param.unwatch(watcher)