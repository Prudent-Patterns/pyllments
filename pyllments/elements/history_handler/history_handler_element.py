from collections import deque

import param
import panel as pn

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.payloads.message.message_payload import MessagePayload
from .history_handler_model import HistoryHandlerModel

# TODO: Allow support of other payload types
class HistoryHandlerElement(Element):
    # TODO Add filtering support
    """
    Responsible for building the context that is sent to the LLM
    Model:
    - history responsible for building context
    - new message
    - context
    Views:
    - current context column
    Ports:
    - input:
        - message_input: MessagePayload - Human and AI messages handled
    - output:
        - messages_output: list[MessagePayload]
    """
    context_view = param.ClassSelector(class_=pn.Column)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = HistoryHandlerModel(**params)
        
        self._message_input_setup()
        self._messages_output_setup()

        self._messages_input_setup()

    def _message_input_setup(self):
        def unpack(payload: MessagePayload): # TODO: Needs to work with list[MessagePayload]
            # If message hasn't streamed:
            # Wait for stream to complete before adding to context
            if payload.model.mode == 'stream' and not payload.model.streamed:
                def stream_callback(event):
                    self.model.load_message(payload)

                payload.model.param.watch(stream_callback, 'streamed')
            else:
                self.model.load_message(payload)
            # Only stage_emit if context isn't an empty list
            if self.model.context:
                self.ports.output['messages_output'].stage_emit(context=self.model.get_context_messages())

        self.ports.add_input(name='message_input', unpack_payload_callback=unpack)

    def _messages_output_setup(self):
        def pack(context: list[MessagePayload]) -> list[MessagePayload]:
            return context
        
        self.ports.add_output(
            name='messages_output',
            pack_payload_callback=pack
        )

    def _messages_input_setup(self):
        def unpack(payload: list[MessagePayload]):
            for message in payload:
                self.model.load_message(message)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    @Component.view
    def create_context_view(
        self, 
        column_css: list = [], 
        container_css: list = [],
        title_css: list = [],
        width: int = None,
        height: int = None,
        sizing_mode: str = 'stretch_both',
        title_visible: bool = True
    ) -> pn.Column:
        """Creates a view for displaying the message history."""
        # Create a separate container for messages
        self.context_container = pn.Column(
            *[msg[0].create_collapsible_view() 
              for msg in self.model.context],
            scroll=True,
            sizing_mode='stretch_both',
            stylesheets=container_css
        )

        # Handle sizing mode
        match (width, height):
            case (None, None):
                pass
            case (_, None):
                sizing_mode = 'stretch_height'
            case (None, _):
                sizing_mode = 'stretch_width'
            case (_, _):
                sizing_mode = 'fixed'

        # Main view column
        self.context_view = pn.Column(
            pn.pane.Markdown(
                "### Current History", 
                visible=title_visible,
                stylesheets=title_css,
                sizing_mode='stretch_width'
            ),
            self.context_container,
            stylesheets=column_css,
            width=width,
            height=height,
            sizing_mode=sizing_mode,
            scroll=False
        )

        async def _update_context_view(event):
            # Create a list to track view updates
            new_objects = [
                msg[0].create_collapsible_view() 
                for msg in self.model.context
            ]
            
            # Update the container objects all at once
            self.context_container.objects = new_objects
            

        # Use Panel's async handler for better FastAPI integration
        self.model.param.watch(_update_context_view, 'context')
        return self.context_view