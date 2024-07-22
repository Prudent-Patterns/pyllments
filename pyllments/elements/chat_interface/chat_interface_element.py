import panel as pn
import param

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.elements.chat_interface import ChatInterfaceModel
from pyllments.payloads.message import MessagePayload
from langchain_core.messages.human import HumanMessage


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
    - output port
        - message_output: MessagePayload
    """

    chatfeed_view = param.ClassSelector(class_=pn.Column, is_instance=True)
    chat_input_view = param.ClassSelector(class_=pn.chat.ChatAreaInput, is_instance=True)
    send_button_view = param.ClassSelector(class_=pn.widgets.Button, is_instance=True)

    def __init__(self, persist=False, **params):
        super().__init__(**params)
        self.model = ChatInterfaceModel(persist=persist)
        
        self._message_output_setup()
        self._message_input_setup()

    def _message_output_setup(self):
        """Sets up the output message port"""
        def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message

        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack)
    
    def _message_input_setup(self):
        """Sets up the input message port"""
        def unpack(payload: MessagePayload):
            self.model.new_message = payload
        
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack)

    @Component.view
    def create_chatfeed_view(self, column_css: str = '', **kwargs):
        """
        Creates and returns a new instance of the chatfeed which
        contains the visual components of the message payloads.
        """
        if self._view_exists(self.chatfeed_view):
            return self.chatfeed_view
        # When first loaded
        self.chatfeed_view = pn.Column(
            stylesheets=[column_css],
            **kwargs)
        message_views = [
            message.create_message_view() 
            for message in self.model.message_list
        ]
        self.chatfeed_view.extend(message_views)

        def _update_chatfeed(event):
            self.chatfeed_view.append(event.new.create_message_view())
        # This watcher should be called before the payload starts streaming.
        self.model.param.watch(_update_chatfeed, 'new_message', precedence=0)
        return self.chatfeed_view

    @Component.view
    def create_chat_input_view(self, input_css: str = '', **kwargs):
        """
        Creates and returns a new instance of ChatAreaInput view.
        """
        if self._view_exists(self.chat_input_view):
            return self.chat_input_view

        self.chat_input_view = pn.chat.ChatAreaInput(
            placeholder='Enter your message',
            rows=3,
            auto_grow=True,
            stylesheets=[input_css],
            **kwargs)
        self.chat_input_view.param.watch(self._on_send, 'value')
        return self.chat_input_view
    
    @Component.view
    def create_send_button_view(
            self,
            button_css: str = '', 
            name: str = 'Send',
            **kwargs):
        """
        Creates and returns a new instance of Button view for sending messages.
        """
        if self._view_exists(self.send_button_view):
            return self.send_button_view

        self.send_button_view = pn.widgets.Button(
            name=name,
            icon='send-2',
            stylesheets=[button_css],
            **kwargs)
        self.send_button_view.on_click(self._on_send)

        return self.send_button_view
    
    @Element.port_stage_emit_if_exists('message_output', 'new_message')
    def _on_send(self, event):
        """
        Handles the send button event by appending the user's message to the chat model,
        clearing the input field, and updating the chat feed view.
        """
        
        if event.obj is self.send_button_view: # When send button is clicked
            if self.chat_input_view:
                input_text = self.chat_input_view.value_input
                self.chat_input_view.value_input = ''
                new_message = MessagePayload(
                    message=HumanMessage(input_text),
                    mode='atomic')
            self.model.new_message = new_message
            
        elif event.obj is self.chat_input_view: # When value changes on 'enter'
            input_text = self.chat_input_view.value
            new_message = MessagePayload(
                message=HumanMessage(input_text),
                mode='atomic')
            self.model.new_message = new_message