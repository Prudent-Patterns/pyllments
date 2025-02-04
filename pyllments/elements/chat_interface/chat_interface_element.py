from typing import Optional

import panel as pn
import param
from langchain_core.messages.human import HumanMessage

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.elements.chat_interface import ChatInterfaceModel
from pyllments.payloads.message import MessagePayload


class ChatInterfaceElement(Element):
    """
    Handles the chat GUI, including the message history, chat input, and send button.
    *****
    Model:
    - messages in the chat
    - message input
    Views:
    - chat feed: 
    - chat input
    - send button:
    Ports:
    - input:
        - message_input: MessagePayload
        - message_emit_input: MessagePayload
    - output port
        - message_output: MessagePayload
    """

    chatfeed_view = param.ClassSelector(class_=pn.Column, is_instance=True)
    chat_input_view = param.ClassSelector(class_=pn.chat.ChatAreaInput, is_instance=True)
    send_button_view = param.ClassSelector(class_=pn.widgets.Button, is_instance=True)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ChatInterfaceModel(**params)
        
        self._message_output_setup()
        self._message_input_setup()
        self._message_emit_input_setup()
    def _message_output_setup(self):
        """Sets up the output message port"""
        def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message

        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack)
    
    def _message_input_setup(self):
        """Sets up the input message port - does not emit from the message_output port"""
        def unpack(payload: MessagePayload):
            self.model.new_message = payload
        
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack)
        
    def _message_emit_input_setup(self):
        """Sets up the message_emit_input port - emits from the message_output port"""
        def unpack(payload: MessagePayload):
            self.model.new_message = payload
            self.ports.output['message_output'].stage_emit(new_message=payload)

        self.ports.add_input(
            name='message_emit_input',
            unpack_payload_callback=unpack)

    @Component.view
    def create_chatfeed_view(self) -> pn.Column:
        """
        Creates and returns a new instance of the chatfeed which
        contains the visual components of the message payloads.
        Needs a height to be set, otherwise it will collapse when
        messages are added.
        """
        self.chatfeed_view = pn.Column(
            scroll=True,
            view_latest=True,
            auto_scroll_limit=1,
            )
        message_views = [
            self.inject_payload_css(
                message.create_static_view,
                show_role=True
                ) 
            for message in self.model.message_list
        ]
        self.chatfeed_view.extend(message_views)

        def _update_chatfeed(event):
            self.chatfeed_view.append(
                self.inject_payload_css(
                    event.new.create_static_view,
                    show_role=True
                )
            )
        # This watcher should be called before the payload starts streaming.
        self.model.param.watch(_update_chatfeed, 'new_message', precedence=0)
        return self.chatfeed_view

    @Component.view
    def create_chat_input_view(self, placeholder: str = 'Yap Here'):
        """
        Creates and returns a new instance of ChatAreaInput view.
        """
        self.chat_input_view = pn.chat.ChatAreaInput(
            placeholder=placeholder,
            auto_grow=True)
        self.chat_input_view.param.watch(self._on_send, 'value')
        return self.chat_input_view
    
    @Component.view
    def create_send_button_view(
        self,
        width: Optional[int] = 38) -> pn.widgets.Button:
        """Creates and returns a new instance of Button view for sending messages."""
        self.send_button_view = pn.widgets.Button(
            icon='send-2',
            icon_size='1.3em')
        self.send_button_view.on_click(self._on_send)

        return self.send_button_view
    
    @Component.view
    def create_chat_input_row_view(self) -> pn.Row:
        """Creates a row containing the chat area input and send button"""
        return pn.Row(
            self.create_chat_input_view(margin=(0, 0, 0, 0)),
            self.create_send_button_view(margin=(0, 0, 0, 10))
            )

    @Component.view
    def create_interface_view(
        self,
        height: int = 800,
        input_height: Optional[int] = 120,
        ) -> pn.Column:
        """Creates a column containing the chat feed and chat input row"""
        margin_top = 10
        return pn.Column(
            self.create_chatfeed_view(height=height - input_height - margin_top),
            self.create_chat_input_row_view(
                height=input_height,
                margin=(margin_top, 0, 0, 0)
                ),
            height=height
        )
    
    @Element.port_stage_emit('message_output', 'new_message')
    def _on_send(self, event):
        """
        Handles the send button event by appending the user's message to the chat model,
        clearing the input field, and updating the chat feed view.
        """
        if event.obj is self.send_button_view:
            if self.chat_input_view:
                input_text = self.chat_input_view.value_input
                self.chat_input_view.value_input = ''
                new_message = MessagePayload(
                    role='user',
                    content=input_text,
                    mode='atomic')
                self.model.new_message = new_message
            
        elif event.obj is self.chat_input_view:
            input_text = self.chat_input_view.value
            new_message = MessagePayload(
                role='user',
                content=input_text,
                mode='atomic')
            self.model.new_message = new_message
