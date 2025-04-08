from collections import deque
from itertools import islice
from typing import Union, List
import asyncio

import param
import panel as pn

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.payloads import MessagePayload, ToolsResponsePayload
from .history_handler_model import HistoryHandlerModel


# TODO: Allow support of other payload types
class HistoryHandlerElement(Element):
    # TODO Add filtering support
    """
    Responsible for building the context that is sent to the LLM, handling both messages and tool responses.
    
    Model:
    - history responsible for building context
    - new message/tool response
    - context
    
    Views:
    - current context column showing messages and tool responses
    
    Ports:
    - input:
        - message_emit_input: MessagePayload - Human and AI messages handled - triggers output of the current context
        - messages_input: MessagePayload | list[MessagePayload] - Messages to add to context
        - tool_response_emit_input: ToolsResponsePayload - Tool responses that trigger output of current context
        - tool_responses_input: ToolsResponsePayload | list[ToolsResponsePayload] - Tool responses to add to context
    - output:
        - history_output: list[Union[MessagePayload, ToolsResponsePayload]] - Current context including both messages and tool responses
    """
    context_view = param.ClassSelector(class_=pn.Column)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = HistoryHandlerModel(**params)
        
        # Message ports
        self._message_emit_input_setup()
        self._messages_input_setup()
        
        # Tool response ports
        self._tool_response_emit_input_setup()
        self._tool_responses_input_setup()
        
        # Output port
        self._history_output_setup()

    def _message_emit_input_setup(self):
        async def unpack(payload: MessagePayload):
            # If message hasn't streamed:
            # Wait for stream to complete before adding to context
            if payload.model.mode == 'stream' and not payload.model.streamed:
                # Create a future to resolve when streaming is complete
                streaming_done = asyncio.Future()
                
                def stream_callback(event):
                    self.model.load_entries([payload])
                    if not streaming_done.done():
                        streaming_done.set_result(True)

                payload.model.param.watch(stream_callback, 'streamed')
                
                # If streaming doesn't complete in a reasonable time, continue anyway
                try:
                    await asyncio.wait_for(streaming_done, timeout=10.0)
                except asyncio.TimeoutError:
                    # Proceed even if streaming hasn't completed
                    self.model.load_entries([payload])
            else:
                self.model.load_entries([payload])
            
            # Only stage_emit if context isn't an empty list
            if self.model.context:
                await self.ports.output['history_output'].stage_emit(context=self.model.get_context_messages())

        self.ports.add_input(name='message_emit_input', unpack_payload_callback=unpack)

    def _messages_input_setup(self):
        async def unpack(payload: Union[List[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            self.model.load_entries(payloads)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    def _tool_response_emit_input_setup(self):
        async def unpack(payload: ToolsResponsePayload):
            # Only process tool responses that have been called or wait for them to be called
            if not payload.model.called:
                # Create a future to resolve when the tool is called
                tool_called = asyncio.Future()
                
                def called_callback(event):
                    if payload.model.tool_responses:  # Only process if there are responses
                        self.model.load_entries([payload])
                        # Only stage_emit if context isn't an empty list
                        if self.model.context:
                            # Create async task since we can't await directly in callback
                            asyncio.create_task(
                                self.ports.output['history_output'].stage_emit(
                                    context=self.model.get_context_messages()
                                )
                            )
                        if not tool_called.done():
                            tool_called.set_result(True)

                payload.model.param.watch(called_callback, 'called')
                
                # If tool isn't called in a reasonable time, continue anyway
                try:
                    await asyncio.wait_for(tool_called, timeout=10.0)
                except asyncio.TimeoutError:
                    # Proceed without waiting further
                    pass
            elif payload.model.tool_responses:  # If already called and has responses, process immediately
                self.model.load_entries([payload])
                # Only stage_emit if context isn't an empty list
                if self.model.context:
                    await self.ports.output['history_output'].stage_emit(context=self.model.get_context_messages())

        self.ports.add_input(name='tool_response_emit_input', unpack_payload_callback=unpack)

    def _tool_responses_input_setup(self):
        async def unpack(payload: Union[List[ToolsResponsePayload], ToolsResponsePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            
            # Split payloads into called and uncalled
            called_payloads = []
            uncalled_payloads = []
            
            for p in payloads:
                if p.model.called and p.model.tool_responses:
                    called_payloads.append(p)
                elif not p.model.called:
                    uncalled_payloads.append(p)
            
            # Process called payloads immediately
            if called_payloads:
                self.model.load_entries(called_payloads)
            
            # Set up watchers for uncalled payloads
            for p in uncalled_payloads:
                def make_called_callback(payload):
                    def called_callback(event):
                        if payload.model.tool_responses:  # Only process if there are responses
                            self.model.load_entries([payload])
                            # We can't await directly in a callback, so use create_task
                            asyncio.create_task(
                                self._handle_tool_response_update()
                            )
                    return called_callback

                p.model.param.watch(make_called_callback(p), 'called')

        self.ports.add_input(name='tool_responses_input', unpack_payload_callback=unpack)
    
    async def _handle_tool_response_update(self):
        """Helper method to handle tool response updates asynchronously"""
        if self.model.context:
            await self.ports.output['history_output'].stage_emit(
                context=self.model.get_context_messages()
            )

    def _history_output_setup(self):
        async def pack(context: List[Union[MessagePayload, ToolsResponsePayload]]) -> List[Union[MessagePayload, ToolsResponsePayload]]:
            """Pack the context messages into a list"""
            return context
        
        self.ports.add_output(
            name='history_output',
            pack_payload_callback=pack,
            payload_type=List[Union[MessagePayload, ToolsResponsePayload]]
        )

    # TODO: Add a view for tool responses
    @Component.view
    def create_context_view(
        self,
        title: str = 'Current History',
        column_css: list = [], 
        container_css: list = [],
        title_css: list = [],
        title_visible: bool = True
    ) -> pn.Column:
        """Creates a view for displaying the message and tool response history."""
        # Create a separate container for messages and tool responses
        self.context_container = pn.Column(
            *[entry[0].create_collapsible_view() if isinstance(entry[0], MessagePayload)
              else entry[0].create_collapsible_view()  # Tool responses should also have a create_collapsible_view method
              for entry in self.model.context],
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
            
            # If entries were removed from the start (sliding window)
            while container_len > current_len:
                del self.context_container.objects[0]  # Remove from start
                container_len -= 1
            
            # Add any new entries at the end
            if current_len > container_len:
                # Use islice to efficiently get only the new entries
                new_views = [
                    entry[0].create_collapsible_view() if isinstance(entry[0], MessagePayload)
                    else entry[0].create_collapsible_view()  # Tool responses should also have a create_collapsible_view method
                    for entry in islice(self.model.context, container_len, None)
                ]
                self.context_container.extend(new_views)
            
            # Ensure visual update
            self.context_container.param.trigger('objects')

        self.model.param.watch(_update_context_view, 'context')
        return self.context_view