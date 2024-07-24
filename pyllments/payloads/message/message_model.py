from typing import Generator, AsyncGenerator
from uuid import uuid4

import param
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.ai import AIMessage

from pyllments.base.model_base import Model
from pyllments.common.tokenizers import get_token_len


class MessageModel(Model):
    # TODO: Finalize if atomic mode should be with message_type and message_text
    # Or with langchain Messages
    message_type = param.Selector(
        default=None, objects=['system', 'ai', 'human'],
        doc="Useful to set for streams. Inferred when LangChain message is passed.")
    message = param.ClassSelector(
        class_=BaseMessage,
        default=BaseMessage(content='', type='placeholder'),
        doc="""Message to be populated""")
    mode = param.Selector(
        objects=['atomic', 'stream'],
        default='stream')
    message_stream = param.ClassSelector(class_=(Generator, AsyncGenerator), doc="""
        Used with stream mode, assumes AI message created from stream""")
    streamed = param.Boolean(default=False, doc="""
        Used to identify if the message has been streamed""")
    id = param.String(doc="""
        Used to identify message""")
    is_multimodal = param.Boolean(doc="""
        Used to identify if the message(s) is multimodal""")
    estimated_token_len = param.Integer(doc="""
        Used to estimate the token length of the message(s)""")
    tokenizer_model = param.String(default='gpt-4o-mini',doc="""
        Used to estimate the token length of the message(s)""")
    tokenization_map = param.Dict(default={},doc="""
        Used to map the model tokenizer to the token len""")

    def __init__(self, **params):
        super().__init__(**params)
        self.id = str(uuid4())
        
        if self.message.type != 'placeholder':
            self.message_type = self.message.type

    def stream(self):
        # TODO Needs async implementation
        if self.mode != 'stream':
            raise ValueError("Cannot stream: Mode is not set to 'stream'")
        self.message = AIMessage(' ') # TODO: REMOVE WHITESPACE
        for chunk in self.message_stream:
            self.message.content += chunk.content
            self.param.trigger('message')
        self.message.response_metadata = chunk.response_metadata
        self.message.id = chunk.id
        self.streamed = True
        # Remove watchers that may have been using streamed
        if (streamed_watchers := self.param.watchers.get('streamed')) is not None:
            for watcher in streamed_watchers['value']:
                self.param.unwatch(watcher)

    def get_token_len(self, model=None, push_stream=False):
        if model in self.tokenization_map:
            return self.tokenization_map[model]
        match self.mode:
            case 'atomic':
                token_length = get_token_len(self.message.content, model)
            case 'stream':
                if push_stream:
                    self.stream() 
                if self.streamed:
                    token_length = get_token_len(self.message.content, model)
                else:
                    raise ValueError("Message has not been streamed")
            case _:
                raise ValueError("Invalid mode: must be 'atomic' or 'stream'")
        
        self.tokenization_map[model] = token_length
        return token_length