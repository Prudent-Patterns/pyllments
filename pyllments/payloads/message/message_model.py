from typing import Generator, AsyncGenerator
from uuid import uuid4

import param
from langchain_core.messages.base import BaseMessage
from langchain_core.messages.ai import AIMessage

from pyllments.base.model_base import Model

class MessageModel(Model):
    # TODO: Finalize if atomic mode should be with message_type and message_text
    # Or with langchain Messages
    message_type = param.Selector(
        default=None, objects=['system', 'ai', 'human'],
        doc="Useful for streams. Inferred when LangChain message is passed.")
    # message_text = param.String(doc="""
    #     Used with atomic mode""")
    message = param.ClassSelector(
        class_=BaseMessage,
        default=BaseMessage(content='', type='placeholder'),
        doc="""Used with atomic mode""")
    mode = param.Selector(
        objects=['atomic', 'stream', 'batch'],
        default='stream')
    message_stream = param.ClassSelector(class_=(Generator, AsyncGenerator), doc="""
        Used with stream mode, assumes AI message created from stream""")
    message_batch = param.List(default=None, item_type=BaseMessage, doc="""
        Used with batch mode, consists of BaseMessages from LangChain""")
    id = param.String(doc="""
        Used to identify message""")

    def __init__(self, **params):
        super().__init__(**params)
        self.id = str(uuid4())
        
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