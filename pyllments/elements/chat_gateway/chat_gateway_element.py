from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

import param

from pyllments.base.element_base import Element
from pyllments.elements.chat_gateway.chat_gateway_model import (
    ChatGatewayModel,
    PendingToolUseState,
)
from pyllments.elements.chat_gateway.pending_tool_use_store import (
    PendingToolUseSnapshot,
    PendingToolUseStore,
)
from pyllments.common.tool_permission import (
    apply_policy_decisions,
    build_tool_result_notice,
    build_tool_use_review,
    normalize_policy_response,
    pending_permission_indices,
    refresh_tool_use_review,
)
from pyllments.elements.chat_gateway.turn_handle import TurnHandle
from pyllments.elements.history_handler.history_store import (
    _deserialize_tool_use,
    _serialize_tool_use,
)
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload
from pyllments.payloads.tool_use import ToolUseExecutorNotBoundError
from pyllments.runtime.scheduler import schedule_task


class ChatGatewayElement(Element):
    """
    Production boundary between application code and Pyllments chat flows.

    Submits user messages into the graph, receives assistant and tool payloads from
    downstream elements, owns permission policy and routing, and exposes tool results
    to application code and downstream history/context wiring.

    The gateway is intentionally a boundary, not a tool executor. Tool calls enter
    through ``tool_use_input`` and are first presented to the application via
    ``on_tool_use(review)``. The gateway then mutates the original
    ``ToolUsePayload`` lifecycle state, calls ``execute_approved()`` on the bound
    payload, and emits one completed ledger on ``tool_result_output`` when all
    tool records are terminal. ``ToolUseElement`` remains responsible for actually
    running the tools through the payload's executor binding.

    User cancellation and replacement messages are handled as branch supersession.
    Each routed tool payload is stamped with an internal ``execution_owner`` token.
    When ``cancel()`` or a new submitted user message supersedes that owner, pending
    permission reviews are cleared and active tool invocations receive cancellation
    through their runtime contexts. Late results from superseded owners still reach
    ``on_tool_result`` as orphaned notices, but they are intentionally suppressed
    from ``tool_result_output`` so history/context/model wiring does not act on
    stale tool output.

    Ports
    -----
    message_output : out
        User ``MessagePayload`` instances into the flow. Calling
        ``submit_message()`` or ``submit_message_async()`` first supersedes prior
        pending/running tool work, then emits the new message.
    assistant_message_input : in
        Assistant ``MessagePayload`` from ``LLMChatElement``.
    tool_use_input : in
        ``ToolUsePayload`` from ``ToolUseElement.tool_use_output``. Every arriving
        payload passes through the application policy gate before execution.
    tool_events_output : out
        Tool-call completion events as ``StructuredPayload``.
    tool_result_output : out
        Active ``ToolUsePayload`` results after execution or denial for
        history/UI/context. Results from superseded owners are not emitted here.
    """

    pending_store = param.Parameter(
        default=None,
        doc=(
            "Optional application-owned PendingToolUseStore used to persist "
            "pending tool permission reviews across process or UI restarts."
        ),
    )

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ChatGatewayModel(**params)
        self._setup_ports()

    def _setup_ports(self):
        self._message_output_setup()
        self._assistant_message_input_setup()
        self._tool_use_input_setup()
        self._tool_events_output_setup()
        self._tool_result_output_setup()

    @staticmethod
    async def _invoke_hook(callback: Callable | None, *args: Any, **kwargs: Any) -> Any:
        """Run a sync or async application hook and return its result."""
        if callback is None:
            return None
        result = callback(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

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

            await self._handle_tool_use_payload(payload)

        self.ports.add_input(
            name="tool_use_input",
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload,
        )

    async def _handle_tool_use_payload(self, payload: ToolUsePayload) -> None:
        """
        Process an arriving tool-use payload through the application policy gate.

        ``on_tool_use(review)`` is the single application boundary for tool calls.
        It receives plain data for all records before execution, whether those
        records require explicit permission or are already approved by policy. The
        callback may return immediate decision data or ``None`` to acknowledge the
        review and leave permission-required records pending.
        """
        review = build_tool_use_review(payload)
        response = await self._invoke_hook(self.model.on_tool_use, review)

        if payload.model.completed:
            return

        if not self._ensure_payload_bound(payload):
            self.logger.warning(
                "ToolUsePayload could not be rebound to executor %s",
                payload.model.executor_element_name,
            )
            payload.model.metadata["execution_owner"] = (
                self.model.current_execution_owner()
            )
            payload.model.metadata["rebind_error"] = (
                f"Executor not found: {payload.model.executor_element_name}"
            )
            await self._emit_tool_result_if_active(payload)
            return

        await self._apply_policy_response(payload, review, response)

    async def _apply_policy_response(
        self,
        payload: ToolUsePayload,
        review: dict[str, Any],
        response: Any,
    ) -> ToolUsePayload | None:
        """
        Apply application policy data and route the payload.

        Decisions are matched against the current ordered subset of tool calls that
        are awaiting permission. Records without pending permission remain in their
        existing state, which lets no-permission tools execute while permission
        tools from the same payload remain pending.
        """
        indices = pending_permission_indices(payload)
        decisions = (
            normalize_policy_response(response, indices)
            if indices
            else None
        )
        if decisions:
            apply_policy_decisions(payload, indices, decisions)

        refresh_tool_use_review(review, payload)
        await self._execute_approved_and_emit_when_complete(payload, review)
        return payload

    @staticmethod
    def _has_executable_approved(payload: ToolUsePayload) -> bool:
        return any(
            record.get("status") == "approved"
            for record in payload.model.tool_calls
        )

    async def _execute_approved_and_emit_when_complete(
        self,
        payload: ToolUsePayload,
        review: dict[str, Any] | None = None,
    ) -> None:
        """
        Run approved records through the bound executor and emit once terminal.

        The gateway stamps each payload with the active internal execution owner
        before execution. The bound executor copies this owner into runtime
        invocation contexts, which is how later cancellation or new-message
        supersession can abort running tools and suppress stale results.
        """
        payload.model.metadata["execution_owner"] = self.model.current_execution_owner()
        if self._has_executable_approved(payload):
            try:
                await payload.execute_approved()
            except ToolUseExecutorNotBoundError as exc:
                self.logger.warning(str(exc))
                payload.model.metadata["rebind_error"] = str(exc)
                for index, record in enumerate(payload.model.tool_calls):
                    if record.get("status") in {
                        "approved",
                        "awaiting_permission",
                        "running",
                    }:
                        payload.model.attach_error(
                            index,
                            {
                                "type": "ToolUseExecutorNotBoundError",
                                "message": str(exc),
                                "retryable": True,
                                "details": {},
                            },
                        )
        if review is None:
            review = build_tool_use_review(payload)
        await self._sync_pending_state(
            payload,
            review,
            payload.model.pending_permission_indices(),
        )
        if payload.model.completed:
            await self._emit_tool_result_if_active(payload)

    async def _emit_tool_result_if_active(self, payload: ToolUsePayload) -> None:
        """Notify the application and emit completed active results downstream."""
        owner = payload.model.metadata.get("execution_owner")
        active = self.model.is_execution_owner_active(owner)
        notice = build_tool_result_notice(payload)
        if not active:
            notice["orphaned"] = True
        await self._invoke_hook(self.model.on_tool_result, notice)
        if active:
            await self.ports.output["tool_result_output"].stage_emit(payload=payload)

    async def _sync_pending_state(
        self,
        payload: ToolUsePayload,
        review: dict[str, Any],
        pending_indices: list[int],
    ) -> None:
        """
        Persist or clear pending tool reviews based on remaining permission state.

        Pending reviews are data-only objects handed to application code. The
        gateway keeps the original review object alive for delayed in-process UI
        resolution and persists only the payload ledger for cold-start recovery.
        """
        existing = self._find_pending_state_for_payload(payload)
        if self.model.tools_need_permission(payload):
            if existing is None:
                state = self.model.register_pending_tool_use(
                    payload,
                    review,
                    pending_indices=payload.model.pending_permission_indices(),
                )
            else:
                state = existing
                state.review = review
                state.pending_indices = payload.model.pending_permission_indices()
            await self._persist_pending_request(state)
            return

        if existing is not None:
            self.model.pop_pending_tool_use(existing.review)
            await self._delete_pending_request(existing)

    def _find_pending_state_for_payload(
        self,
        payload: ToolUsePayload,
    ) -> PendingToolUseState | None:
        for state in self.model._pending_tool_uses:
            if state.payload is payload:
                return state
        return None

    def _ensure_payload_bound(self, payload: ToolUsePayload) -> bool:
        if payload.is_bound:
            return True
        return payload.bind_registered_executor()

    async def _persist_pending_request(self, state: PendingToolUseState) -> None:
        if self.pending_store is None:
            return
        now = time.time()
        if state.pending_snapshot is None:
            state.pending_snapshot = PendingToolUseSnapshot(
                payload_data=_serialize_tool_use(state.payload),
                created_at=now,
                updated_at=now,
            )
        else:
            state.pending_snapshot.payload_data = _serialize_tool_use(state.payload)
            state.pending_snapshot.updated_at = now
        state.pending_snapshot = await self.pending_store.save_pending_tool_use(
            state.pending_snapshot
        )

    async def _delete_pending_request(self, state: PendingToolUseState) -> None:
        if self.pending_store is None or state.pending_snapshot is None:
            return
        await self.pending_store.clear_pending_tool_use(state.pending_snapshot)
        state.pending_snapshot = None

    async def _clear_pending_tool_uses(self, *, reason: str) -> None:
        """
        Drop pending permission reviews and cancel their unresolved tool records.

        This is used when a user cancels the turn or submits a replacement message.
        The app should no longer resolve those reviews because they belong to a
        stale conversational branch.
        """
        for state in self.model.pop_all_pending_tool_uses():
            state.payload.model.cancel_non_terminal_calls(
                state.pending_indices,
                reason=reason,
            )
            await self._delete_pending_request(state)

    async def _cancel_running_tools(self, execution_owner: str) -> None:
        """Propagate cancellation to ToolUseElement invocations for an owner."""
        await ToolUsePayload.cancel_execution_for_owner(execution_owner)

    async def _abort_branch_tool_work(
        self,
        execution_owner: str | None,
        *,
        reason: str,
    ) -> None:
        """
        Clear pending reviews and cancel running tools for a superseded branch.

        Pending decisions are removed immediately. Running tools receive cooperative
        cancellation through their ``ToolInvocationContext`` and may stop, drain, or
        detach depending on their interrupt policy. Any late result is treated as
        orphaned by active-result filtering.
        """
        await self._clear_pending_tool_uses(reason=reason)
        if execution_owner:
            await self._cancel_running_tools(execution_owner)

    async def _prepare_new_user_message(self) -> str:
        """
        Supersede prior tool work before emitting a new user message.

        A new user message means the user has moved the conversation to a fresh
        branch. Previous permission prompts and running tool calls should no longer
        influence model/history/context state for the new branch.
        """
        previous_owner, new_owner = self.model.begin_new_execution_branch()
        if previous_owner:
            await self._abort_branch_tool_work(
                previous_owner,
                reason="Superseded by new user message",
            )
        return new_owner

    def _tool_events_output_setup(self):
        async def pack(payload: dict) -> StructuredPayload:
            return StructuredPayload(data=payload)

        self.ports.add_output(name="tool_events_output", pack_payload_callback=pack)

    def _tool_result_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(name="tool_result_output", pack_payload_callback=pack)

    async def emit_tool_event(self, turn_id: str, tool_calls: list[dict]) -> None:
        """
        Emit streamed tool-call completion for downstream tool routing.

        ``TurnHandle.stream()`` calls this when the assistant stream produces a
        ``tool_calls_complete`` event. The emitted structured payload is a routing
        event; it is not itself a permission decision or execution result.
        """
        if self.model.is_turn_cancelled(turn_id):
            return
        event = {"tool_calls": tool_calls}
        await self._invoke_hook(self.model.on_tool_event, event)
        await self.ports.output["tool_events_output"].stage_emit(payload=event)

    async def resolve_tool_use(
        self,
        review: dict[str, Any],
        decisions: list[dict[str, Any]] | dict[str, Any],
    ) -> ToolUsePayload | None:
        """
        Apply delayed application decisions to a pending tool review.

        This is the durable/data-contract counterpart to immediate
        ``on_tool_use(review)`` responses. The application passes back the same
        review object it previously received plus ordered decision data. If the
        review was superseded by cancellation or a new message, the gateway returns
        ``None`` and emits nothing.

        Returns
        -------
        ToolUsePayload or None
            The updated payload, or None if ``review`` is no longer pending.
        """
        state = self.model.get_pending_tool_use(review)
        if state is None:
            self.logger.warning("Unknown or already-resolved tool review")
            return None

        if not self._ensure_payload_bound(state.payload):
            self.logger.warning(
                "Cannot resolve tool review: executor %s unavailable",
                state.payload.model.executor_element_name,
            )
            return None

        normalized = normalize_policy_response(decisions, state.pending_indices)
        if normalized is None:
            return None

        apply_policy_decisions(state.payload, state.pending_indices, normalized)
        refresh_tool_use_review(state.review, state.payload)
        await self._execute_approved_and_emit_when_complete(
            state.payload,
            state.review,
        )

        return state.payload

    async def hydrate_pending_tool_uses(self) -> list[dict[str, Any]]:
        """
        Restore pending tool reviews from the optional pending store.

        Rebinds executors when available, recovers stale running records, and
        invokes ``on_pending_tool_use_restored`` for each restored review.
        Hydration restores application-visible review data only for payloads that
        still require permission; already-resolved or unbindable records are purged
        from the store.
        """
        if self.pending_store is None:
            return []

        restored: list[dict[str, Any]] = []
        snapshots = await self.pending_store.load_pending_tool_uses()
        for snapshot in snapshots:
            payload = _deserialize_tool_use(snapshot.payload_data)
            payload.model.recover_stale_running()

            if not self._ensure_payload_bound(payload):
                self.logger.warning(
                    "Pending tool review could not rebind executor %s; purging",
                    payload.model.executor_element_name,
                )
                payload.model.metadata["rebind_error"] = (
                    f"Executor not found: {payload.model.executor_element_name}"
                )
                await self.pending_store.clear_pending_tool_use(snapshot)
                continue

            indices = payload.model.pending_permission_indices()
            if not indices:
                await self.pending_store.clear_pending_tool_use(snapshot)
                continue

            review = build_tool_use_review(payload)
            state = PendingToolUseState(
                payload=payload,
                review=review,
                pending_indices=indices,
                pending_snapshot=snapshot,
            )
            self.model._pending_tool_uses.append(state)
            restored.append(review)
            await self._invoke_hook(
                self.model.on_pending_tool_use_restored,
                review,
            )

        return restored

    def resolve_tool_use_sync(
        self,
        review: dict[str, Any],
        decisions: list[dict[str, Any]] | dict[str, Any],
    ) -> None:
        """Schedule :meth:`resolve_tool_use` on the runtime loop."""
        schedule_task(self.resolve_tool_use(review, decisions))

    async def submit_message_async(
        self,
        content: str,
        role: str = "user",
        **kwargs,
    ) -> TurnHandle:
        """
        Submit a user message and await its emission onto ``message_output``.

        Submission starts a new execution branch. Before the user message enters
        the graph, the gateway clears stale permission prompts and asks running
        tools from the previous branch to cancel. This keeps a replacement user
        message from racing against tool output that the backend should ignore.
        """
        await self._prepare_new_user_message()
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

        This synchronous convenience method schedules the same branch-supersession
        workflow as ``submit_message_async()`` before emitting the message. Use the
        returned ``TurnHandle`` for live stream consumption and cancellation; do not
        use it as durable application identity.

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
            await self._prepare_new_user_message()
            await self._invoke_hook(
                self.model.on_user_message_submitted,
                user_message,
                turn_id,
            )
            await self.ports.output["message_output"].stage_emit(payload=user_message)

        schedule_task(_emit())
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def cancel(self, turn_id: str) -> None:
        """
        Cancel an in-flight turn and supersede its tool work.

        Cancellation stops the linked assistant stream when possible, clears any
        pending tool permission reviews, and forwards cancellation to active tool
        invocations for the current execution owner. Late tool results can still be
        observed by ``on_tool_result`` as orphaned notices, but they are suppressed
        from ``tool_result_output`` so downstream backend flow does not act on them.
        """
        self.model.cancel_turn(turn_id)
        owner = self.model.current_execution_owner()
        self.model.supersede_owner(owner)

        async def _abort():
            await self._abort_branch_tool_work(owner, reason="Turn cancelled by user")

        schedule_task(_abort())
