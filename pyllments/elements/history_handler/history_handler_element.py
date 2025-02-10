from collections import deque
from itertools import islice
from typing import Union
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
        - message_emit_input: MessagePayload - Human and AI messages handled - triggers output of the current context
        - messages_input: MessagePayload | list[MessagePayload] - Messages to add to context
    - output:
        - messages_output: list[MessagePayload]
    """
    context_view = param.ClassSelector(class_=pn.Column)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = HistoryHandlerModel(**params)
        
        self._message_emit_input_setup()
        self._messages_output_setup()

        self._messages_input_setup()

    def _message_emit_input_setup(self):
        def unpack(payload: MessagePayload):
            # If message hasn't streamed:
            # Wait for stream to complete before adding to context
            if payload.model.mode == 'stream' and not payload.model.streamed:
                def stream_callback(event):
                    self.model.load_messages([payload])

                payload.model.param.watch(stream_callback, 'streamed')
            else:
                self.model.load_messages([payload])
            
            # Only stage_emit if context isn't an empty list
            if self.model.context:
                self.ports.output['messages_output'].stage_emit(context=self.model.get_context_messages())

        self.ports.add_input(name='message_emit_input', unpack_payload_callback=unpack)

    def _messages_input_setup(self): # TODO: need better port naming
        def unpack(payload: Union[list[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            self.model.load_messages(payloads)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    def _messages_output_setup(self):
        def pack(context: list[MessagePayload]) -> list[MessagePayload]:
            return context
        
        self.ports.add_output(
            name='messages_output',
            pack_payload_callback=pack
        )

    @Component.view
    def create_context_view(
        self,
        title: str = 'Current History',
        column_css: list = [], 
        container_css: list = [],
        title_css: list = [],
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
        # Main view column
        self.context_view = pn.Column(
            pn.pane.Markdown(
                f"### {title}", 
                visible=title_visible,
                stylesheets=title_css,
                sizing_mode='stretch_width'
            ),
            self.context_container,
            stylesheets=column_css,
            scroll=False
        )

        async def _update_context_view(event):
            current_len = len(self.model.context)
            container_len = len(self.context_container.objects)
            
            # If messages were removed from the start (sliding window)
            while container_len > current_len:
                del self.context_container.objects[0]  # Remove from start
                container_len -= 1
            
            # Add any new messages at the end
            if current_len > container_len:
                # Use islice to efficiently get only the new messages
                new_views = [
                    msg[0].create_collapsible_view()
                    for msg in islice(self.model.context, container_len, None)
                ]
                self.context_container.extend(new_views)
            
            # Ensure visual update
            self.context_container.param.trigger('objects')

        self.model.param.watch(_update_context_view, 'context')
        return self.context_view