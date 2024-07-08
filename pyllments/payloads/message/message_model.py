import param
from langchain_core.messages.base import BaseMessage

from pyllments.base.model_base import Model

class MessageModel(Model):
    # TODO: Finalize if atomic mode should be with message_type and message_text
    # Or with langchain Messages
    message_type = param.Selector(
        default=None, objects=['system', 'ai', 'human'],
        doc="Useful for streams. Inferred when message is passed.")
    # message_text = param.String(doc="""
    #     Used with atomic mode""")
    message = param.ClassSelector(
        class_=BaseMessage,
        doc="""Used with atomic mode""")
    mode = param.Selector(
        objects=['atomic', 'stream', 'batch'],
        default='stream',
        )
    # message_stream = param.Parameter(default=None, doc="""
    #     Used with stream mode""")
    message_batch = param.List(default=None, item_type=BaseMessage, doc="""
        Used with batch mode, consists of BaseMessages from LangChain""")

    def stream(self):
        # TODO Needs async implementation
        if self.mode != 'stream':
            raise ValueError("Cannot stream: Mode is not set to 'stream'")
        for seg in self.stream_obj:
            self.message_text += seg