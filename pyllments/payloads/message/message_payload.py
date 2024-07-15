import param
import panel as pn
from typing import Literal, Optional, Generator, AsyncGenerator
from langchain_core.messages import BaseMessage

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload
from pyllments.payloads.message.message_model import MessageModel

class MessagePayload(Payload):
    model = param.ClassSelector(class_=MessageModel, is_instance=True)
    message_view = param.ClassSelector(class_=pn.Row, is_instance=True)
    
    def __init__(
            self,
            message_type: Literal['human', 'system', 'ai'] = 'human',
            message: BaseMessage = BaseMessage(content=' '*10, type='placeholder'),
            message_stream: Optional[Generator | AsyncGenerator] = None,
            mode: Literal['stream', 'atomic'] = 'stream',
            **params):
        super().__init__(**params)
        # self.model = self.model.class_(
        self.model = MessageModel(
            message_type=message_type,
            message=message,
            message_stream=message_stream,
            mode=mode)

    @Component.view
    def create_message_view(
        self,
        markdown_css: Optional[str] = None,
        row_css: Optional[str] = None) -> pn.Row:
        """Creates a message container"""
        markdown = pn.pane.Markdown(
            self.model.message.content,
            stylesheets=[markdown_css])
        self.message_view = pn.Row(markdown, stylesheets=[row_css])
        self.model.param.watch(self._update_message_view, 'message')
        return self.message_view
    
    def _update_message_view(self, event):
        # Changes the text of the markdown object directly within the message
        self.message_view[0].object = self.model.message.content
        
