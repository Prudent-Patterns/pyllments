import param
import panel as pn
from typing import Literal, Optional, Generator, AsyncGenerator
from langchain_core.messages import BaseMessage
from loguru import logger

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
        user_markdown_css: list = [],
        user_row_css: list = [],
        assistant_markdown_css: list = [],
        assistant_row_css: list = [],
        role_css: list = [],
        show_role: bool = True,
        sizing_mode: Literal['fixed', 'stretch_width', 'stretch_height', 'stretch_both'] = 'stretch_width'
        ) -> pn.Row:
        """Creates a message container"""
        match self.model.role:
            case 'user':
                markdown_css = user_markdown_css
                row_css = user_row_css
                role_str = 'User'
            case 'assistant':
                markdown_css = assistant_markdown_css
                row_css = assistant_row_css
                role_str = 'Assistant'
            case 'system':
                markdown_css = user_markdown_css
                row_css = user_row_css
                role_str = 'System'
            case _:  # Handle other roles
                markdown_css = user_markdown_css
                row_css = user_row_css
                role_str = self.model.role.capitalize()

        markdown = pn.pane.Markdown(
            self.model.content,  # Changed from message.content
            stylesheets=markdown_css)

        def _update_message_view(event):
            view[0].object = self.model.content
        self.model.param.watch(_update_message_view, 'content')
        
        if show_role:
            role_md = pn.pane.Markdown(role_str, stylesheets=role_css)
            view = pn.Row(markdown, role_md, stylesheets=row_css)
        else:
            view = pn.Row(markdown, stylesheets=row_css)
        return view

    @Component.view
    def create_collapsible_view(
        self,
        markdown_css: list = [],
        user_row_css: list = [],
        assistant_row_css: list = [],
        role_css: list = [],
        button_css: list = [],
        show_role: bool = True,
        truncation_length: int = 65,
        sizing_mode = 'stretch_width'
        ) -> pn.Row:
        """Creates a message container"""
        match self.model.role:
            case 'user':
                row_css = user_row_css
                role_str = 'User'
            case 'assistant':
                row_css = assistant_row_css
                role_str = 'Assistant'
            case 'system':
                row_css = user_row_css
                role_str = 'System'
            case _:  # Handle other roles
                row_css = user_row_css
                role_str = self.model.role.capitalize()

        expand_button = pn.widgets.Toggle(
            icon='plus',
            icon_size='1.1em',
            button_type='primary',
            button_style='outline',
            stylesheets=button_css)

        markdown = pn.pane.Markdown(
            self.model.content if len(self.model.content) <= truncation_length 
            else f"{self.model.content[:truncation_length]}...",  # Add ellipsis to show truncation
            stylesheets=markdown_css)
 
        def _update_message_view(event):
            current_content = self.model.content
            if not current_content:
                return
                
            if expand_button.value:
                # Show full content if expanded
                markdown.object = current_content
            else:
                # Show beginning of content with ellipsis if needed
                markdown.object = (current_content if len(current_content) <= truncation_length 
                                else f"{current_content[:truncation_length]}...")

        self.model.param.watch(_update_message_view, 'content')

        def toggle_visibility(event):
            if event.new:  # If the toggle is activated
                expand_button.icon = 'minus'
                markdown.object = self.model.content
            else:  # If the toggle is deactivated
                expand_button.icon = 'plus'
                markdown.object = (self.model.content if len(self.model.content) <= truncation_length 
                                 else f"{self.model.content[:truncation_length]}...")
        expand_button.param.watch(toggle_visibility, 'value')

        row_args = [expand_button, markdown]
        if show_role:
            role_md = pn.pane.Markdown(
                role_str, stylesheets=role_css)
            row_args.append(role_md)
        view = pn.Row(
            *row_args, stylesheets=row_css,
            sizing_mode='stretch_width')    
        return view 