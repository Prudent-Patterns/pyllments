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
from pyllments.runtime.loop_registry import LoopRegistry


# TODO: Allow support of other payload types
class HistoryHandlerElement(Element):
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
        - message_emit_input: MessagePayload - Human and AI messages handled - triggers output of the message context
        - messages_input: MessagePayload | list[MessagePayload] - Messages to add to context
        - tool_response_emit_input: ToolsResponsePayload - Tool responses that trigger output of tool response context
        - tools_responses_input: ToolsResponsePayload | list[ToolsResponsePayload] - Tool responses to add to context
    - output:
        - message_history_output: List[MessagePayload] - Current message context
    """
    # TODO Add filtering support
    show_tool_responses = param.Boolean(default=False, doc="Whether to include tool response views in the context view")
    context_view = param.ClassSelector(class_=pn.Column)

    def __init__(self, **params):
        super().__init__(**params)
        self.model = HistoryHandlerModel(**params)
        
        # Message ports
        self._message_emit_input_setup()
        self._messages_input_setup()
        
        # Tool response ports
        self._tool_response_emit_input_setup()
        self._tools_responses_input_setup()
        
        # Output ports
        self._message_history_output_setup()

    def _message_emit_input_setup(self):
        async def unpack(payload: MessagePayload):
            # schedule background task to update history without blocking other ports
            async def _handle():
                await payload.model.await_ready()
                self.model.load_entries([payload])
                await self.ports.output['message_history_output'].stage_emit(
                    context=self.model.get_context_message_payloads()
                )
            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name='message_emit_input', unpack_payload_callback=unpack)

    def _messages_input_setup(self):
        async def unpack(payload: Union[List[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            # schedule background task to update history without blocking other ports
            async def _handle():
                for p in payloads:
                    await p.model.await_ready()
                self.model.load_entries(payloads)
            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    def _tool_response_emit_input_setup(self):
        async def unpack(payload: ToolsResponsePayload):
            # schedule background task to update history without blocking other ports
            async def _handle():
                await payload.model.await_ready()
                self.model.load_entries([payload])
                await self.ports.output['message_history_output'].stage_emit(
                    context=self.model.get_context_message_payloads()
                )
            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name='tool_response_emit_input', unpack_payload_callback=unpack)

    def _tools_responses_input_setup(self):
        async def unpack(payload: Union[List[ToolsResponsePayload], ToolsResponsePayload]):
            items = payload if isinstance(payload, list) else [payload]
            # schedule background task to update history without blocking other ports
            async def _handle():
                for item in items:
                    await item.model.await_ready()
                self.model.load_entries(items)
            LoopRegistry.get_loop().create_task(_handle())

        self.ports.add_input(name='tools_responses_input', unpack_payload_callback=unpack)
    
    def _message_history_output_setup(self):
        async def pack(context: list[MessagePayload]) -> list[MessagePayload]:
            """Pack the message context into a list"""
            return context
        
        # Use built-in list generic to align with conversion mapping
        self.ports.add_output(
            name='message_history_output',
            pack_payload_callback=pack,
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
        # Build a list of views: always show messages, optionally tool responses
        views = []
        for entry, _ in self.model.context:
            if isinstance(entry, MessagePayload):
                views.append(entry.create_collapsible_view())
            elif self.show_tool_responses and isinstance(entry, ToolsResponsePayload):
                # Only include tool response views when enabled
                views.append(entry.create_collapsible_view())
        # Create the context container column
        context_container = pn.Column(
            *views,
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
            context_container,
            stylesheets=column_css,
            scroll=False
        )

        async def _update_context_view(event):
            current_len = len(self.model.context)
            # Access the objects list of the context container directly
            container_len = len(context_container.objects)
            
            # If entries were removed from the start (sliding window)
            while container_len > current_len:
                del context_container.objects[0]  # Remove from start
                container_len -= 1
            
            # Add any new entries at the end
            if current_len > container_len:
                # Build only the new views, respecting the show_tool_responses flag
                new_views = []
                for entry, _ in islice(self.model.context, container_len, None):
                    if isinstance(entry, MessagePayload):
                        new_views.append(entry.create_collapsible_view())
                    elif self.show_tool_responses and isinstance(entry, ToolsResponsePayload):
                        new_views.append(entry.create_collapsible_view())
                context_container.extend(new_views)
            
            # Ensure visual update
            context_container.param.trigger('objects')

        # Track updates to context; decorator handles cleanup on rebuild
        self.watch(self.model, 'context', _update_context_view)
        return self.context_view