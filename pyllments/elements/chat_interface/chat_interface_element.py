from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING

import param

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.common.tool_permission import (
    build_tool_use_review,
    pending_permission_indices,
    refresh_tool_use_review,
)
from pyllments.elements.chat_interface import ChatInterfaceModel
from pyllments.payloads import MessagePayload, ToolUsePayload
from pyllments.payloads.tool_use import ToolUseExecutorNotBoundError
from pyllments.runtime.scheduler import schedule_task

if TYPE_CHECKING:
    import panel as pn


class ChatInterfaceElement(Element):
    """
    Handles the chat GUI, including message history, chat input, and send button.
    
    Model:
    - messages in the chat
    
    Views:
    - chat feed
    - chat input
    - send button
    
    Ports:
    - input:
        - message_input: MessagePayload         # display only (no downstream emit)
        - message_emit_input: MessagePayload    # display and then emit based on role
        - tool_use_input: ToolUsePayload        # display, gate, and execute approved tools
        - tool_result_input: ToolUsePayload      # display/forward completed tool results
        - tool_use_emit_input: ToolUsePayload    # compatibility alias for terminal results
    - output:
        - user_message_output: MessagePayload
        - assistant_message_output: MessagePayload
        - message_output: MessagePayload        # unified port for both user and assistant messages
        - tool_result_output: ToolUsePayload     # completed full tool-use ledger
        - tool_use_output: ToolUsePayload        # compatibility alias for tool_result_output
    """

    def __init__(self, **params):
        super().__init__(**params)
        self.chatfeed_view = None
        self.chat_input_view = None
        self.send_button_view = None
        self._rendered_payload_indices: dict[int, int] = {}
        self._tool_payload_watchers: dict[int, object] = {}
        self.model = ChatInterfaceModel(**params)
        
        # Set up ports for messages and tool responses
        self._user_message_output_setup()
        self._assistant_message_output_setup()
        # Input-only ports (no emit)
        self._message_input_setup()
        self._message_emit_input_setup()
        self._tool_use_input_setup()
        self._tool_result_input_setup()
        self._tool_use_emit_input_setup()
        self._tool_result_output_setup()
        self._tool_use_output_setup()
        # Unified output port for both user and assistant messages
        self._message_output_setup()
        self._tool_message_output_setup()

    def _user_message_output_setup(self):
        """Sets up an output port for user-originated MessagePayloads."""
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload
        self.ports.add_output(
            name='user_message_output',
            pack_payload_callback=pack)

    def _assistant_message_output_setup(self):
        """Sets up an output port for assistant-originated MessagePayloads."""
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload
        self.ports.add_output(
            name='assistant_message_output',
            pack_payload_callback=pack)
    
    def _message_input_setup(self):
        """Sets up an input port for displaying MessagePayloads (no emit)."""
        async def unpack(payload: MessagePayload):
            await self.model.add_message(payload)
        self.ports.add_input(
            name='message_input',
            unpack_payload_callback=unpack)

    def _message_emit_input_setup(self):
        """Sets up an input port for emitting MessagePayloads after display."""
        async def unpack(payload: MessagePayload):
            await self.model.add_message(payload)
            # Emit to role-specific ports
            port = 'user_message_output' if payload.model.role == 'user' else 'assistant_message_output'
            await self.ports.output[port].stage_emit(payload=payload)
            # Emit unified message port
            await self.ports.output['message_output'].stage_emit(payload=payload)
            if payload.model.tool_calls:
                await self.ports.output['tool_message_output'].stage_emit(payload=payload)
        self.ports.add_input(
            name='message_emit_input',
            unpack_payload_callback=unpack)
    
    def _tool_use_input_setup(self):
        """Sets up the Panel-native policy gate for proposed tool uses."""
        async def unpack(payload: ToolUsePayload):
            self._watch_tool_payload(payload)
            await self.model.add_message(payload)
            await self._handle_tool_use_payload(payload)
        self.ports.add_input(
            name='tool_use_input',
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload)

    def _tool_result_input_setup(self):
        """Receives externally executed terminal tool payloads."""
        async def unpack(payload: ToolUsePayload):
            await self._handle_tool_result_payload(payload)
        self.ports.add_input(
            name='tool_result_input',
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload)

    def _tool_use_emit_input_setup(self):
        """Compatibility alias for older result-only tool-use wiring."""
        async def unpack(payload: ToolUsePayload):
            await self._handle_tool_result_payload(payload)
        self.ports.add_input(
            name='tool_use_emit_input',
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload)

    def _tool_result_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(
            name='tool_result_output',
            pack_payload_callback=pack)

    def _tool_use_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(
            name='tool_use_output',
            pack_payload_callback=pack)

    def _message_output_setup(self):
        """Sets up a unified output port for user and assistant MessagePayloads."""
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload
        self.ports.add_output(
            name='message_output',
            pack_payload_callback=pack)

    def _tool_message_output_setup(self):
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload
        self.ports.add_output(
            name='tool_message_output',
            pack_payload_callback=pack)

    def _watch_tool_payload(self, payload: ToolUsePayload):
        """Refresh the existing feed card when tool lifecycle state mutates."""
        key = id(payload)
        if key in self._tool_payload_watchers:
            return

        def _refresh(_event):
            self.model.refresh_payload(payload)

        watcher = payload.model.param.watch(_refresh, ['updated_at', 'status', 'completed'])
        self._tool_payload_watchers[key] = watcher

    @staticmethod
    def _has_executable_approved(payload: ToolUsePayload) -> bool:
        return any(
            record.get('status') == 'approved'
            for record in payload.model.tool_calls
        )

    async def _handle_tool_use_payload(self, payload: ToolUsePayload):
        """
        Display and route a proposed tool-use payload from the Panel boundary.

        The payload itself remains the execution contract: the chat interface mutates
        approval state, calls ``execute_approved()``, and emits a single terminal
        ledger downstream when all tool records are complete.
        """
        review = build_tool_use_review(payload)
        await self._sync_pending_state(payload, review)
        await self._execute_approved_and_emit_when_complete(payload)

    async def _handle_tool_result_payload(self, payload: ToolUsePayload):
        """Display and forward a completed tool payload when it belongs to this branch."""
        self._watch_tool_payload(payload)
        await self.model.add_message(payload)
        await payload.model.await_ready()
        await self._emit_tool_result_if_active(payload)

    async def _execute_approved_and_emit_when_complete(self, payload: ToolUsePayload):
        """Run approved records through the bound executor and emit once terminal."""
        payload.model.metadata['execution_owner'] = self.model.current_execution_owner()
        if self._has_executable_approved(payload):
            try:
                await payload.execute_approved()
            except ToolUseExecutorNotBoundError as exc:
                self.logger.warning(str(exc))
                payload.model.metadata['rebind_error'] = str(exc)
                for index, record in enumerate(payload.model.tool_calls):
                    if record.get('status') in {'approved', 'awaiting_permission', 'running'}:
                        payload.model.attach_error(
                            index,
                            {
                                'type': 'ToolUseExecutorNotBoundError',
                                'message': str(exc),
                                'retryable': True,
                                'details': {},
                            },
                        )
        await self._sync_pending_state(payload)
        if payload.model.completed:
            await self._emit_tool_result_if_active(payload)

    async def _emit_tool_result_if_active(self, payload: ToolUsePayload):
        """Emit completed active results on both new and compatibility outputs."""
        owner = payload.model.metadata.get('execution_owner')
        self.model.refresh_payload(payload)
        if not self.model.is_execution_owner_active(owner):
            return
        await self.ports.output['tool_result_output'].stage_emit(payload=payload)
        await self.ports.output['tool_use_output'].stage_emit(payload=payload)

    async def _sync_pending_state(
        self,
        payload: ToolUsePayload,
        review: dict | None = None,
    ):
        """Keep in-memory pending permission state aligned with payload status."""
        existing = self.model.find_pending_tool_use(payload)
        if self.model.tools_need_permission(payload):
            pending_indices = pending_permission_indices(payload)
            if review is None:
                review = existing.review if existing is not None else build_tool_use_review(payload)
            refresh_tool_use_review(review, payload)
            if existing is None:
                self.model.register_pending_tool_use(
                    payload,
                    review,
                    pending_indices=pending_indices,
                )
            else:
                existing.review = review
                existing.pending_indices = pending_indices
            return

        if existing is not None:
            self.model.pop_pending_tool_use(payload)

    async def approve_tool_use(self, payload: ToolUsePayload):
        """Approve all currently pending tool calls for a displayed payload."""
        indices = payload.model.pending_permission_indices()
        if not indices:
            return
        payload.model.approve(indices, decided_by='user')
        await self._sync_pending_state(payload)
        await self._execute_approved_and_emit_when_complete(payload)

    async def deny_tool_use(self, payload: ToolUsePayload, reason: str | None = None):
        """Deny all currently pending tool calls for a displayed payload."""
        indices = payload.model.pending_permission_indices()
        if not indices:
            return
        payload.model.deny(indices, reason=reason, decided_by='user')
        await self._sync_pending_state(payload)
        if payload.model.completed:
            await self._emit_tool_result_if_active(payload)

    async def _clear_pending_tool_uses(self, *, reason: str):
        """Cancel unresolved permission prompts for a superseded chat branch."""
        for state in self.model.pop_all_pending_tool_uses():
            state.payload.model.cancel_non_terminal_calls(
                state.pending_indices,
                reason=reason,
            )
            self.model.refresh_payload(state.payload)

    async def _prepare_new_user_message(self):
        """Supersede previous pending/running tool work before sending a new message."""
        previous_owner, _new_owner = self.model.begin_new_execution_branch()
        await self._clear_pending_tool_uses(reason='Superseded by new user message')
        if previous_owner:
            await ToolUsePayload.cancel_execution_for_owner(previous_owner)

    def _render_chatfeed_item(self, payload: MessagePayload | ToolUsePayload):
        if isinstance(payload, MessagePayload):
            return self.inject_payload_css(
                payload.create_static_view,
                show_role=True
            )
        return self.create_tool_use_decision_view(payload)

    def _upsert_chatfeed_item(self, payload: MessagePayload | ToolUsePayload):
        if isinstance(payload, MessagePayload) and not payload.model.content and payload.model.tool_calls:
            return
        key = id(payload)
        view = self._render_chatfeed_item(payload)
        if key in self._rendered_payload_indices:
            index = self._rendered_payload_indices[key]
            if self.chatfeed_view is not None and index < len(self.chatfeed_view.objects):
                self.chatfeed_view.objects[index] = view
                self.chatfeed_view.param.trigger('objects')
            return
        self._rendered_payload_indices[key] = len(self.chatfeed_view.objects)
        self.chatfeed_view.append(view)

    @Component.view
    def create_tool_use_decision_view(self, payload: ToolUsePayload) -> pn.Column:
        """Render a tool-use card with simple approve/deny controls when actionable."""
        pending_indices = payload.model.pending_permission_indices()
        tool_view = payload.create_tool_use_view()
        if not pending_indices:
            return pn.Column(tool_view)

        reason_input = pn.widgets.TextInput(
            placeholder='Optional denial reason',
            sizing_mode='stretch_width',
        )
        approve_button = pn.widgets.Button(name='Approve all', button_type='primary')
        deny_button = pn.widgets.Button(name='Deny all', button_type='warning')

        def _disable_controls():
            approve_button.disabled = True
            deny_button.disabled = True
            reason_input.disabled = True

        def _approve(_event):
            _disable_controls()
            schedule_task(self.approve_tool_use(payload))

        def _deny(_event):
            _disable_controls()
            schedule_task(self.deny_tool_use(payload, reason=reason_input.value or None))

        approve_button.on_click(_approve)
        deny_button.on_click(_deny)

        return pn.Column(
            tool_view,
            pn.Row(approve_button, deny_button),
            reason_input,
        )

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
        self._rendered_payload_indices = {}
        for message in self.model.message_list:
            if isinstance(message, ToolUsePayload):
                self._watch_tool_payload(message)
            self._upsert_chatfeed_item(message)

        async def _update_chatfeed(event):
            updated_list = event.new
            if not isinstance(updated_list, list) or not updated_list:
                return
            new_item = updated_list[-1]
            if isinstance(new_item, ToolUsePayload):
                self._watch_tool_payload(new_item)
                self._upsert_chatfeed_item(new_item)
                return
            if isinstance(new_item, MessagePayload):
                if not new_item.model.content and new_item.model.tool_calls:
                    return  # Skip rendering messages with only tool calls
                if id(new_item) in self._rendered_payload_indices:
                    self._upsert_chatfeed_item(new_item)
                    return
                fake_it = (
                    new_item.model.role == 'assistant' and 
                    (new_item.model.mode == 'atomic' or new_item.model.streamed)
                    )
                if fake_it:
                    loaded_content = new_item.model.content
                    new_item.model.content = ''

                self._upsert_chatfeed_item(new_item)
                if fake_it:
                    for i in range(0, len(loaded_content), 8):  # Load 8 characters at a time
                        new_item.model.content += loaded_content[i:i + 8]  # Concatenate the next 8 characters to the content
                        await asyncio.sleep(0.05)
                    new_item.model.content = loaded_content

        self.watch(self.model, 'message_list', _update_chatfeed)
        return self.chatfeed_view

    @Component.view
    def create_chat_input_view(self, placeholder: str = 'Yap Here') -> pn.chat.ChatAreaInput:
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
        input_height: Optional[int] = 120,
        ) -> pn.Column:
        """Creates a column containing the chat feed and chat input row"""
        return pn.Column(
            self.create_chatfeed_view(),
            pn.Spacer(height=10),
            self.create_chat_input_row_view(
                height=input_height,
                margin=(0, 0, 0, 0)
                )
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

        await self._prepare_new_user_message()
            
        # Create and send the message via centralized handler
        new_message = MessagePayload(
            role='user',
            content=input_text,
            mode='atomic')
        await self.model.add_message(new_message)
        
        # Explicitly stage and emit to both role-specific and unified ports
        await self.ports.output['user_message_output'].stage_emit(payload=new_message)
        await self.ports.output['message_output'].stage_emit(payload=new_message)