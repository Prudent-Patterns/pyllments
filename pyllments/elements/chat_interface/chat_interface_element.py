import asyncio
from typing import Optional
from venv import create

import panel as pn
import param
from loguru import logger

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.elements.chat_interface import ChatInterfaceModel
from pyllments.payloads import MessagePayload, ToolsResponsePayload
from pyllments.common.loop_registry import LoopRegistry

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
        - tools_response_input: ToolsResponsePayload
    - output:
        - message_output: MessagePayload
        - tools_response_output: ToolsResponsePayload
    """

    chatfeed_view = param.ClassSelector(class_=pn.Column, is_instance=True)
    chat_input_view = param.ClassSelector(class_=pn.chat.ChatAreaInput, is_instance=True)
    send_button_view = param.ClassSelector(class_=pn.widgets.Button, is_instance=True)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ChatInterfaceModel(**params)
        
        # Set up ports for messages and tool responses
        self._message_output_setup()
        self._message_input_setup()
        self._message_emit_input_setup()
        self._tools_response_emit_input_setup()
        self._tools_response_output_setup()

    def _message_output_setup(self):
        """Sets up the output message port"""
        async def pack(new_message: MessagePayload) -> MessagePayload:
            return new_message

        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack)
    
    def _message_input_setup(self):
        """Sets up the input message port - does not emit from the message_output port"""
        async def unpack(payload: MessagePayload):
            await self.model.add_message(payload)
        
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack)
        
    def _message_emit_input_setup(self):
        """Sets up the message_emit_input port - emits from the message_output port"""
        async def unpack(payload: MessagePayload):
            await self.model.add_message(payload)
            await self.ports.output['message_output'].stage_emit(new_message=payload)

        self.ports.add_input(
            name='message_emit_input',
            unpack_payload_callback=unpack)
    
    def _tools_response_emit_input_setup(self):
        async def unpack(payload: ToolsResponsePayload):
            # Add the payload to the chat model and immediately stage for emit
            await self.model.add_message(payload)
            await self.ports.output['tools_response_output'].stage_emit(payload=payload)

        self.ports.add_input(
            name='tools_response_emit_input',
            unpack_payload_callback=unpack)
        
    def _tools_response_output_setup(self):
        """Sets up the output port for tool responses"""
        async def pack(payload: ToolsResponsePayload) -> ToolsResponsePayload:
            # Defer actual emission until payload is fully ready
            await payload.model.await_ready()
            return payload

        self.ports.add_output(
            name='tools_response_output',
            pack_payload_callback=pack)

    @Component.view
    def create_chatfeed_view(self) -> pn.Column:
        """
        create and returns a new instance of the chatfeed which
        contains the visual components of the message payloads.
        Needs a height to be set, otherwise it will collapse when
        messages are added.
        """
        self.chatfeed_view = pn.Column(
            scroll=True,
            view_latest=True,
            auto_scroll_limit=1,
            )
        message_and_tool_response_views = []
        for message in self.model.message_list:
            if isinstance(message, MessagePayload):
                message_and_tool_response_views.append(
                    self.inject_payload_css(
                        message.create_static_view,
                        show_role=True
                    )
                )
            elif isinstance(message, ToolsResponsePayload):
                message_and_tool_response_views.append(
                    message.create_tool_response_view()
                )

        self.chatfeed_view.extend(message_and_tool_response_views)
        async def _update_chatfeed(event):
            # event.new is the updated message_list; extract the last appended payload
            updated_list = event.new
            if not isinstance(updated_list, list) or not updated_list:
                return
            new_item = updated_list[-1]
            if isinstance(new_item, MessagePayload):
                fake_it = (
                    new_item.model.role == 'assistant' and 
                    (new_item.model.mode == 'atomic' or new_item.model.streamed)
                    )
                if fake_it:
                    loaded_content = new_item.model.content
                    new_item.model.content = ''

                self.chatfeed_view.append(
                    self.inject_payload_css(
                        new_item.create_static_view,
                        show_role=True
                    )
                )
                if fake_it:
                    for i in range(0, len(loaded_content), 8):  # Load 8 characters at a time
                        new_item.model.content += loaded_content[i:i + 8]  # Concatenate the next 8 characters to the content
                        await asyncio.sleep(0.05)
                    new_item.model.content = loaded_content

            elif isinstance(new_item, ToolsResponsePayload):
                # Append the dynamic tool response view, which has its own prompt logic
                self.chatfeed_view.append(new_item.create_tool_response_view())

        # This watcher should be called before the payload starts streaming.
        self.watch_once(_update_chatfeed, 'message_list', precedence=0)
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
    
    async def _on_send(self, event):
        """
        Handles the send button event by appending the user's message to the chat model,
        clearing the input field, and updating the chat feed view.
        """
        # Get the input text from the appropriate source
        input_text = None
        
        if event.obj is self.send_button_view:
            if self.chat_input_view:
                input_text = self.chat_input_view.value_input
                self.chat_input_view.value_input = ''
                
        elif event.obj is self.chat_input_view:
            # Use value_input for both cases to get what the user typed,
            # not value (which is apparently empty on Enter key press)
            input_text = self.chat_input_view.value_input
            self.chat_input_view.value_input = ''
            
        # Skip if the input is empty
        if not input_text or input_text.strip() == '':
            return
            
        # Create and send the message via centralized handler
        new_message = MessagePayload(
            role='user',
            content=input_text,
            mode='atomic')
        await self.model.add_message(new_message)
        
        # Explicitly stage and emit
        await self.ports.output['message_output'].stage_emit(new_message=new_message)
