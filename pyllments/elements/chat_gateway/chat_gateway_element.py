from __future__ import annotations

import asyncio
from typing import Any, Callable

import param

from pyllments.base.element_base import Element
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload
from pyllments.runtime.loop_registry import LoopRegistry
from pyllments.elements.chat_gateway.chat_gateway_model import ChatGatewayModel
from pyllments.elements.chat_gateway.turn_handle import TurnHandle


class ChatGatewayElement(Element):
    """
    Production boundary between application code and Pyllments chat flows.

    Submits user messages into the graph, receives assistant and tool payloads from
    downstream elements, surfaces optional hooks to the host app, and emits approved
    or denied tool decisions back into the flow. Does not execute tool callables.

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
    tool_use_approved_output : out
        ``ToolUsePayload`` after the application approves a permission request.
    tool_use_denied_output : out
        ``ToolUsePayload`` with denied tool-use records for downstream routing.
    """

    default_aggregate_stream = param.Boolean(
        default=True,
        doc="Default aggregate_stream for assistant stream payloads (history compatibility)",
    )

    _ELEMENT_PARAMS = frozenset({"default_aggregate_stream"})

    def __init__(self, **params):
        super().__init__(**params)
        model_params = {
            key: value
            for key, value in params.items()
            if key not in self._ELEMENT_PARAMS
        }
        self.model = ChatGatewayModel(**model_params)
        self._setup_ports()

    def _setup_ports(self):
        self._message_output_setup()
        self._assistant_message_input_setup()
        self._tool_use_input_setup()
        self._tool_events_output_setup()
        self._tool_use_approved_output_setup()
        self._tool_use_denied_output_setup()

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

            await self._invoke_hook(
                self.model.on_tool_use,
                payload,
                turn_id,
            )

            if self.model.tools_need_permission(payload):
                perm_state = self.model.register_permission_request(turn_id, payload)
                await self._invoke_hook(
                    self.model.on_permission_request,
                    self.model.build_permission_request_event(perm_state),
                    turn_id,
                )
                return

        self.ports.add_input(
            name="tool_use_input",
            unpack_payload_callback=unpack,
            payload_type=ToolUsePayload,
        )

    def _tool_events_output_setup(self):
        async def pack(payload: dict) -> StructuredPayload:
            return StructuredPayload(data=payload)

        self.ports.add_output(name="tool_events_output", pack_payload_callback=pack)

    def _tool_use_approved_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(
            name="tool_use_approved_output",
            pack_payload_callback=pack,
        )

    def _tool_use_denied_output_setup(self):
        async def pack(payload: ToolUsePayload) -> ToolUsePayload:
            return payload

        self.ports.add_output(
            name="tool_use_denied_output",
            pack_payload_callback=pack,
        )

    async def emit_tool_event(self, turn_id: str, tool_calls: list[dict]) -> None:
        """Emit tool-call completion for downstream tool routing."""
        if self.model.is_turn_cancelled(turn_id):
            return
        event = {"turn_id": turn_id, "tool_calls": tool_calls}
        await self._invoke_hook(self.model.on_tool_event, event, turn_id)
        await self.ports.output["tool_events_output"].stage_emit(payload=event)

    async def approve_permission_request(self, request_id: str) -> ToolUsePayload | None:
        """
        Approve a pending tool permission and emit the payload into the flow.

        Returns
        -------
        ToolUsePayload or None
            The approved payload, or None if ``request_id`` is unknown.
        """
        state = self.model.pop_permission_request(request_id)
        if state is None:
            self.logger.warning("Unknown permission request id: %s", request_id)
            return None

        state.payload.model.approve()
        await self.ports.output["tool_use_approved_output"].stage_emit(
            payload=state.payload
        )
        return state.payload

    async def deny_permission_request(
        self,
        request_id: str,
        reason: str | None = None,
    ) -> ToolUsePayload | None:
        """
        Deny a pending tool permission and emit a denied ToolUsePayload into the flow.

        Returns
        -------
        ToolUsePayload or None
            The denied payload, or None if ``request_id`` is unknown.
        """
        state = self.model.pop_permission_request(request_id)
        if state is None:
            self.logger.warning("Unknown permission request id: %s", request_id)
            return None

        state.payload.model.deny(reason=reason)
        state.payload.model.metadata["denial_reason"] = reason
        await self.ports.output["tool_use_denied_output"].stage_emit(payload=state.payload)
        return state.payload

    def approve_permission_request_sync(self, request_id: str) -> None:
        """Schedule :meth:`approve_permission_request` on the runtime loop."""
        LoopRegistry.get_loop().create_task(self.approve_permission_request(request_id))

    def deny_permission_request_sync(
        self,
        request_id: str,
        reason: str | None = None,
    ) -> None:
        """Schedule :meth:`deny_permission_request` on the runtime loop."""
        LoopRegistry.get_loop().create_task(
            self.deny_permission_request(request_id, reason=reason)
        )

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
            correlation_id=turn_id,
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
            correlation_id=turn_id,
            **kwargs,
        )
        self.model.register_turn(turn_id, user_message)

        loop = LoopRegistry.get_loop()

        async def _emit():
            await self._invoke_hook(
                self.model.on_user_message_submitted,
                user_message,
                turn_id,
            )
            await self.ports.output["message_output"].stage_emit(payload=user_message)

        loop.create_task(_emit())
        return TurnHandle(turn_id=turn_id, user_message=user_message, gateway=self)

    def cancel(self, turn_id: str) -> None:
        """Cancel an in-flight turn by id."""
        self.model.cancel_turn(turn_id)
