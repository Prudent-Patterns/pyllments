from typing import Generator, AsyncGenerator
from uuid import uuid4
import asyncio

import param
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.ai import AIMessage
from loguru import logger # TODO: remove after debugging

from pyllments.base.model_base import Model
from pyllments.common.tokenizers import get_token_len


class MessageModel(Model):
    # TODO: Finalize if atomic mode should be with role and message_text
    # Or with langchain Messages
    role = param.Selector(
        default='human', objects=['system', 'ai', 'human'],
        doc="Useful to set for streams. Inferred when LangChain message is passed.")
    message = param.ClassSelector(
        class_=BaseMessage,
        default=BaseMessage(content='', type='placeholder'),
        doc="""Message to be populated""")
    mode = param.Selector(
        objects=['atomic', 'stream'],
        default='atomic')
    message_stream = param.ClassSelector(class_=(Generator, AsyncGenerator), doc="""
        Used with stream mode, assumes AI message created from stream""")
    streamed = param.Boolean(default=False, doc="""
        Used to identify if the message has been streamed""")
    id = param.String(doc="""
        Used to identify message""")
    is_multimodal = param.Boolean(default=False, doc="""
        Used to identify if the message(s) is multimodal""")

    embedding = param.Parameter(doc=""" # TODO: Type this properly
        Embedding of message - likely ndarray(np.float32)""")

    def __init__(self, **params):
        super().__init__(**params)
        # self.id = str(uuid4()) # TODO: Why? Remove if no udk
        
        if self.message.type != 'placeholder':
            self.role = self.message.type

    async def stream(self):
        if self.mode != 'stream':
            raise ValueError("Cannot stream: Mode is not set to 'stream'")
        self.message = AIMessage(' ') # TODO: REMOVE WHITESPACE
        logger.info(f"Entering the langchain stream") # TODO: remove after debugging
        async for chunk in self.message_stream:
            self.message.content += chunk.content
            self.param.trigger('message')
        logger.info(f"Exiting the langchain stream") # TODO: remove after debugging
        self.message.response_metadata = chunk.response_metadata
        self.message.id = chunk.id
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
            return self.message
            
        if self.streamed:
            return self.message
            
        done_future = asyncio.Future()
        
        def on_streamed_change(event):
            if event.new and not done_future.done():
                done_future.set_result(self.message)
        
        watcher = self.param.watch(on_streamed_change, 'streamed')
        try:
            return await done_future
        finally:
            self.param.unwatch(watcher)
