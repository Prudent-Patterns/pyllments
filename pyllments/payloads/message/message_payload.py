import param
import panel as pn
from typing import Literal, Optional, Generator, AsyncGenerator
from langchain_core.messages import BaseMessage

from pyllments.base.component_base import Component
from pyllments.base.payload_base import Payload
from pyllments.payloads.message.message_model import MessageModel


class MessagePayload(Payload):
        
    def __init__(self, **params):
        super().__init__(**params)
        self.model = MessageModel(**params)

    @Component.view
    def create_static_view(
        self,
        human_markdown_css: list = [],
        human_row_css: list = [],
        ai_markdown_css: list = [],
        ai_row_css: list = [],
        role_css: list = [],
        show_role: bool = True
        ) -> pn.Row:
        """Creates a message container"""
        match self.model.role:
            case 'human':
                markdown_css = human_markdown_css
                row_css = human_row_css
                role_str = 'Human'
            case 'ai':
                markdown_css = ai_markdown_css
                row_css = ai_row_css
                role_str = 'AI'
        markdown = pn.pane.Markdown(
            self.model.message.content,
            stylesheets=markdown_css)
 

        def _update_message_view(event):
            view[0].object = self.model.message.content
        self.model.param.watch(_update_message_view, 'message')
        if show_role:
            role_md = pn.pane.Markdown(
                role_str, stylesheets=role_css)
            view = pn.Row(
                markdown, role_md, stylesheets=row_css,
                sizing_mode='stretch_width')
        else:
            view = pn.Row(
                markdown, stylesheets=row_css,
                sizing_mode='stretch_width')
        return view
    
    @Component.view
    def create_collapsible_view(
        self,
        human_markdown_css: list = [],
        human_row_css: list = [],
        ai_markdown_css: list = [],
        ai_row_css: list = [],
        role_css: list = [],
        button_css: list = [],
        show_role: bool = True,
        truncation_length: int = 40
        ) -> pn.Row:
        """Creates a message container"""
        match self.model.role:
            case 'human':
                markdown_css = human_markdown_css
                row_css = human_row_css
                role_str = 'Human'
            case 'ai':
                markdown_css = ai_markdown_css
                row_css = ai_row_css
                role_str = 'AI'

        expand_button = pn.widgets.Toggle(
            icon='plus',
            icon_size='1.1em',
            button_type='primary',
            button_style='outline',
            stylesheets=button_css)

        markdown = pn.pane.Markdown(
            self.model.message.content[:truncation_length],
            stylesheets=markdown_css)
 
        def _update_message_view(event):
            #TODO Handle for streaming scenarios
            view[0].object = self.model.message.content
        self.model.param.watch(_update_message_view, 'message')

        def toggle_visibility(event):
            if event.new:  # If the toggle is activated
                expand_button.icon = 'minus'
                markdown.object = self.model.message.content
            else:  # If the toggle is deactivated
                expand_button.icon = 'plus'
                markdown.object = self.model.message.content[:truncation_length]
        expand_button.param.watch(toggle_visibility, 'value')

        row_args = [expand_button, markdown]
        # row_args = [markdown]
        if show_role:
            role_md = pn.pane.Markdown(
                role_str, stylesheets=role_css)
            row_args.append(role_md)
        view = pn.Row(
            *row_args, stylesheets=row_css,
            sizing_mode='stretch_width')    
        return view 
    