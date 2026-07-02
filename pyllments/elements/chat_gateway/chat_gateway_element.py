from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import param

from pyllments.base.element_base import Element
from pyllments.elements.chat_gateway.chat_gateway_model import (
    ChatGatewayModel,
    PermissionRequestState,
)
from pyllments.elements.chat_gateway.pending_tool_use_store import (
    PendingToolUseRecord,
    PendingToolUseStore,
    SQLitePendingToolUseStore,
)
from pyllments.elements.chat_gateway.tool_permission import (
    ToolPermissionRequest,
    ToolUseNotice,
)
from pyllments.elements.chat_gateway.turn_handle import TurnHandle
from pyllments.elements.history_handler.history_store import (
    _deserialize_tool_use,
    _serialize_tool_use,
)
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload
from pyllments.runtime.scheduler import schedule_task


class ChatGatewayElement(Element):
    """
    Production boundary between application code and Pyllments chat flows.

    Submits user messages into the graph, receives assistant and tool payloads from
    downstream elements, owns permission and execution timing, and emits tool results
    for UI/history/context wiring.

    Ports
    -----
    message_output : out
        User ``MessagePayload`` instances into the flow.
    assistant_message_input : in
        Assistant ``MessagePayload`` from ``LLMChatElement``.
    tool_use_input : in
        ``ToolUsePayload`` from tool lifecycle (pending, completed, or informational).
    tool_events_output : out
        Tool-call completion events as ``StructuredPayload``.
    tool_result_output : out
        ``ToolUsePayload`` after gateway execution or denial.
    """

    default_aggregate_stream = param.Boolean(
        default=True,
        doc="Default aggregate_stream for assistant stream payloads (history compatibility)",
    )
    pending_db_path = param.String(
        default=None,
        allow_None=True,
        doc="Optional SQLite path for pending tool permission persistence.",
    )

    _ELEMENT_PARAMS = frozenset({"default_aggregate_stream", "pending_db_path"})

    def __init__(self, **params):
        pending_store = params.pop("pending_store", None)
        super().__init__(**params)
        model_params = {
            key: value
            for key, value in params.items()
            if key not in self._ELEMENT_PARAMS
        }
        self.model = ChatGatewayModel(**model_params)
        if pending_store is not None:
            self.pending_store = pending_store
        elif self.pending_db_path:
            self.pending_store = SQLitePendingToolUseStore(db_path=self.pending_db_path)
        else:
            self.pending_store = None
        self._setup_ports()

    def _setup_ports(self):
        self._message_output_setup()
        self._assistant_message_input_setup()
        self._tool_use_input_setup()
        self._tool_events_output_setup()
        self._tool_result_output_setup()

    @staticmethod
    async def _invoke_hook(callback: Callable | None, *args: Any, **kwargs: Any) -> None:
        """Run a sync or async application hook."""
        if callback is None:
            return
        result = callback(*args, **kwargs)
        if asyncio.iscoroutine(result):
            await result

    def _message_output_setup(self):
        async def pack(payload: MessagePayload) -> MessagePayload:
            return payload

        self.ports.add_output(name="message_output", pack_payload_callback=pack)

    def _assistant_message_input_setup(self):
        async def unpack(payload: MessagePayload):
            turn_id = self.model.match_turn(payload)
            if turn_id is None:
                self.logger.warning(
                    "Received assistant message with no pending turn; ignoring"
                )
                return

            state = self.model.get_turn_state(turn_id)
            if state is None or state.cancelled:
                payload.model.cancel()
                return

            if payload.model.mode == "stream":
                payload.model.aggregate_stream = self.default_aggregate_stream

            await self._invoke_hook(
                self.model.on_assistant_message,
                payload,
                turn_id,
            )

        self.ports.add_input(
            name="assistant_message_input",
            unpack_payload_callback=unpack,
            payload_type=MessagePayload,
        )

    def _tool_use_input_setup(self):
        async def unpack(payload: ToolUsePayload):
            turn_id = self.model.resolve_turn_id_for_tools(payload)
            if turn_id is None:
                self.logger.warning(
                    "Received tool use payload with no resolvable turn; ignoring"
                )
                return

            await self._handle_tool_use_payload(payload, turn_id)

        self.ports.add_input(
            name="tool_use_input",
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload,
        )

    async def _handle_tool_use_payload(self, payload: ToolUsePayload, turn_id: str) -> None:
        """Process an arriving tool-use payload: hook, execute, and gate permissions."""
        notice = ToolUseNotice.from_payload(payload)
        await self._invoke_hook(self.model.on_tool_use, notice)

        if payload.model.completed:
            return

        if not self._ensure_payload_bound(payload):
            self.logger.warning(
                "ToolUsePayload could not be rebound to executor %s",
                payload.model.executor_element_name,
            )
            payload.model.metadata["rebind_error"] = (
                f"Executor not found: {payload.model.executor_element_name}"
            )
            await self._emit_tool_result(payload)
            return

        approved_indices = self._executable_tool_call_indices(payload)
        if approved_indices:
            await self._execute_and_emit(payload, approved_indices)

        if self.model.tools_need_permission(payload):
            perm_state = self.model.register_permission_request(payload)
            await self._persist_pending_request(perm_state)
            await self._invoke_hook(
                self.model.on_permission_request,
                perm_state.request,
            )
            if perm_state.request.has_decisions:
                await self.resolve_permission_request(perm_state.request)

    def _ensure_payload_bound(self, payload: ToolUsePayload) -> bool:
        if payload.is_bound:
            return True
        return payload.bind_registered_executor()

    @staticmethod
    def _executable_tool_call_indices(payload: ToolUsePayload) -> list[int]:
        return [
            index
            for index, record in enumerate(payload.model.tool_calls)
            if record.get("status") == "approved"
        ]

    async def _execute_and_emit(
        self,
        payload: ToolUsePayload,
        tool_call_indices: list[int] | None = None,
    ) -> ToolUsePayload:
        executed = await self._execute_tool_calls(payload, tool_call_indices)
        await self._emit_tool_result(executed)
        return executed

    async def _execute_tool_calls(
        self,
        payload: ToolUsePayload,
        tool_call_indices: list[int] | None = None,
    ) -> ToolUsePayload:
        return await payload.execute_approved(tool_call_indices=tool_call_indices)

    async def _emit_tool_result(self, payload: ToolUsePayload) -> None:
        await self.ports.output["tool_result_output"].stage_emit(payload=payload)

    async def _persist_pending_request(self, state: PermissionRequestState) -> None:
        if self.pending_store is None:
            return
        now = time.time()
        if state.pending_record is None:
            state.pending_record = PendingToolUseRecord(
                payload_data=_serialize_tool_use(state.payload),
                created_at=now,
                updated_at=now,
            )
        else:
            state.pending_record.payload_data = _serialize_tool_use(state.payload)
            state.pending_record.updated_at = now
        await self.pending_store.upsert_record(state.pending_record)

    async def _delete_pending_request(self, state: PermissionRequestState) -> None:
        if self.pending_store is None or state.pending_record is None:
            return
        await self.pending_store.delete_record(state.pending_record)
        state.pending_record = None

    async def _sync_pending_request(self, state: PermissionRequestState) -> None:
        if self.model.tools_need_permission(state.payload):
            await self._persist_pending_request(state)
        else:
            await self._delete_pending_request(state)

    def _tool_events_output_setup(self):
        async def pack(payload: dict) -> StructuredPayload:
            return StructuredPayload(data=payload)

        self.ports.add_output(name="tool_events_output", pack_payload_callback=pack)

    def _tool_result_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(name="tool_result_output", pack_payload_callback=pack)

    async def emit_tool_event(self, turn_id: str, tool_calls: list[dict]) -> None:
        """Emit tool-call completion for downstream tool routing."""
        if self.model.is_turn_cancelled(turn_id):
            return
        event = {"tool_calls": tool_calls}
        await self._invoke_hook(self.model.on_tool_event, event)
        await self.ports.output["tool_events_output"].stage_emit(payload=event)

    async def resolve_permission_request(
        self,
        request: ToolPermissionRequest,
    ) -> ToolUsePayload | None:
        """
        Apply application decisions from a permission request object.

        Returns
        -------
        ToolUsePayload or None
            The updated payload, or None if ``request`` is no longer pending.
        """
        state = self.model.get_permission_request(request)
        if state is None:
            self.logger.warning("Unknown or already-resolved permission request")
            return None

        if not self._ensure_payload_bound(state.payload):
            self.logger.warning(
                "Cannot resolve permission request: executor %s unavailable",
                state.payload.model.executor_element_name,
            )
            return None

        approved_indices = [tool.index for tool in request.approved_tools]
        denied_tools = request.denied_tools
        if approved_indices:
            await self._execute_tool_calls(state.payload, approved_indices)

        if self.model.tools_need_permission(state.payload):
            state.pending_indices = self.model.pending_permission_indices(state.payload)
            await self._sync_pending_request(state)
        else:
            self.model.pop_permission_request(request)
            await self._delete_pending_request(state)

        if approved_indices or denied_tools:
            await self._emit_tool_result(state.payload)
        return state.payload

    async def hydrate_pending_tool_uses(self) -> list[ToolPermissionRequest]:
        """
        Restore pending permission requests from the optional pending store.

        Rebinds executors when available, recovers stale running records, and
        invokes ``on_pending_permission_restored`` for each restored request.
        """
        if self.pending_store is None:
            return []

        restored: list[ToolPermissionRequest] = []
        records = await self.pending_store.load_records()
        for record in records:
            payload = _deserialize_tool_use(record.payload_data)
            payload.model.recover_stale_running()

            if not self._ensure_payload_bound(payload):
                self.logger.warning(
                    "Pending tool request could not rebind executor %s; purging",
                    payload.model.executor_element_name,
                )
                payload.model.metadata["rebind_error"] = (
                    f"Executor not found: {payload.model.executor_element_name}"
                )
                await self.pending_store.delete_record(record)
                continue

            pending_indices = self.model.pending_permission_indices(payload)
            if not pending_indices:
                await self.pending_store.delete_record(record)
                continue

            request = ToolPermissionRequest.from_payload(payload)
            state = PermissionRequestState(
                payload=payload,
                request=request,
                pending_indices=pending_indices,
                pending_record=record,
            )
            self.model._permission_requests.append(state)
            restored.append(request)
            await self._invoke_hook(
                self.model.on_pending_permission_restored,
                request,
            )
            if request.has_decisions:
                await self.resolve_permission_request(request)

        return restored

    def resolve_permission_request_sync(self, request: ToolPermissionRequest) -> None:
        """Schedule :meth:`resolve_permission_request` on the runtime loop."""
        schedule_task(self.resolve_permission_request(request))

    async def submit_message_async(
        self,
        content: str,
        role: str = "user",
        **kwargs,
    ) -> TurnHandle:
        """Async variant that awaits emission onto ``message_output``."""
        turn_id = self.model.create_turn_id()
        user_message = MessagePayload(
            content=content,
            role=role,
            **kwargs,
        )
        self.model.register_turn(turn_id, user_message)
        await self._invoke_hook(
            self.model.on_user_message_submitted,
            user_message,
            turn_id,
        )
        await self.ports.output["message_output"].stage_emit(payload=user_message)
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def submit_message(self, content: str, role: str = "user", **kwargs) -> TurnHandle:
        """
        Inject a user message into the flow and return a turn handle.

        Parameters
        ----------
        content : str
            Message text.
        role : str
            Message role (default ``user``).
        **kwargs
            Additional ``MessagePayload`` / ``MessageModel`` parameters.

        Returns
        -------
        TurnHandle
            Handle for streaming and cancellation.
        """
        turn_id = self.model.create_turn_id()
        user_message = MessagePayload(
            content=content,
            role=role,
            **kwargs,
        )
        self.model.register_turn(turn_id, user_message)

        async def _emit():
            await self._invoke_hook(
                self.model.on_user_message_submitted,
                user_message,
                turn_id,
            )
            await self.ports.output["message_output"].stage_emit(payload=user_message)

        schedule_task(_emit())
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def cancel(self, turn_id: str) -> None:
        """Cancel an in-flight turn by id."""
        self.model.cancel_turn(turn_id)
