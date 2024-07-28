import param
import panel as pn
from typing import Literal, Optional, Generator, AsyncGenerator
from langchain_core.messages import BaseMessage

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload
from pyllments.payloads.message.message_model import MessageModel


class MessagePayload(Payload):
    model = param.ClassSelector(class_=MessageModel)
    
    def __init__(
            self,
            role: Literal['human', 'system', 'ai'] = 'human',
            message: BaseMessage = BaseMessage(content='', type='placeholder'),
            mode: Literal['stream', 'atomic', 'batch'] = 'stream',
            message_stream: Optional[Generator | AsyncGenerator] = None,
            is_multimodal: bool = False,
            **params):
        super().__init__(**params)
        self.model = MessageModel(
            role=role,
            message=message,
            message_stream=message_stream,
            mode=mode,
            is_multimodal=is_multimodal)

    @Component.view
    def create_message_view(
        self,
        human_markdown_css: list = [],
        human_row_css: list = [],
        ai_markdown_css: list = [],
        ai_row_css: list = []
        ) -> pn.Row:
        """Creates a message container"""
        match self.model.role:
            case 'human':
                markdown_css = human_markdown_css
                row_css = human_row_css
            case 'ai':
                markdown_css = ai_markdown_css
                row_css = ai_row_css
        markdown = pn.pane.Markdown(
            self.model.message.content,
            stylesheets=markdown_css)
        def _update_message_view(event):
            view[0].object = self.model.message.content
        self.model.param.watch(_update_message_view, 'message')
        view = pn.Row(markdown, stylesheets=row_css)
        return view