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
from pyllments.common.loop_registry import LoopRegistry  # use our loop registry for event loop


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
        - message_emit_input: MessagePayload - Human and AI messages handled - triggers output of the message context
        - messages_input: MessagePayload | list[MessagePayload] - Messages to add to context
        - tool_response_emit_input: ToolsResponsePayload - Tool responses that trigger output of tool response context
        - tool_responses_input: ToolsResponsePayload | list[ToolsResponsePayload] - Tool responses to add to context
    - output:
        - message_history_output: List[MessagePayload] - Current message context
        - tool_response_history_output: List[ToolsResponsePayload] - Current tool response context
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
        
        # Output ports
        self._message_history_output_setup()
        self._tool_response_history_output_setup()
        # Watch for context changes to emit history asynchronously
        self.model.param.watch(self._emit_all_history, 'context')

    def _message_emit_input_setup(self):
        async def unpack(payload: MessagePayload):
            # Load into history/context; emission is triggered by context watcher
            self.model.load_entries([payload])
            # For streaming payloads, load entries again when stream completes
            if getattr(payload.model, 'mode', None) == 'stream':
                def on_streamed(event):
                    self.model.load_entries([payload])
                payload.model.param.watch(on_streamed, 'streamed')

        self.ports.add_input(name='message_emit_input', unpack_payload_callback=unpack)

    def _messages_input_setup(self):
        async def unpack(payload: Union[List[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            self.model.load_entries(payloads)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    def _tool_response_emit_input_setup(self):
        async def unpack(payload: ToolsResponsePayload):
            # Load tool response; emission is triggered by context watcher
            self.model.load_entries([payload])
            # For tool calls still pending, load entries when call completes
            if not payload.model.called:
                def on_called(event):
                    if payload.model.tool_responses:
                        self.model.load_entries([payload])
                payload.model.param.watch(on_called, 'called')

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
                            # Schedule history update using our LoopRegistry
                            LoopRegistry.get_loop().create_task(
                                self._handle_tool_response_update()  # This will emit tool response history
                            )
                    return called_callback

                p.model.param.watch(make_called_callback(p), 'called')

        self.ports.add_input(name='tool_responses_input', unpack_payload_callback=unpack)
    
    async def _handle_tool_response_update(self):
        """Helper method to handle tool response updates asynchronously"""
        # no-op: context watcher handles emissions
        return

    def _message_history_output_setup(self):
        async def pack(context: List[MessagePayload]) -> List[MessagePayload]:
            """Pack the message context into a list"""
            return context
        
        self.ports.add_output(
            name='message_history_output',
            pack_payload_callback=pack,
            payload_type=List[MessagePayload]
        )

    def _tool_response_history_output_setup(self):
        async def pack(context: List[ToolsResponsePayload]) -> List[ToolsResponsePayload]:
            """Pack the tool response context into a list"""
            return context
        
        self.ports.add_output(
            name='tool_response_history_output',
            pack_payload_callback=pack,
            payload_type=List[ToolsResponsePayload]
        )

    def _emit_all_history(self, event):
        """Watch context changes and emit both message and tool response history."""
        # Emit message history
        LoopRegistry.get_loop().create_task(
            self.ports.output['message_history_output'].stage_emit(
                context=self.model.get_context_message_payloads()
            )
        )
        # Emit tool response history
        LoopRegistry.get_loop().create_task(
            self.ports.output['tool_response_history_output'].stage_emit(
                context=self.model.get_context_tool_response_payloads()
            )
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