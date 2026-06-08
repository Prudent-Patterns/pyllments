from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

import param

from pyllments.base.model_base import Model

if TYPE_CHECKING:
    from pyllments.payloads import MessagePayload, ToolUsePayload


@dataclass
class TurnState:
    """Per-turn runtime state (not exposed via Param)."""

    turn_id: str
    user_message: MessagePayload
    assistant_message: MessagePayload | None = None
    cancelled: bool = False
    done: bool = False
    assistant_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class PermissionRequestState:
    """Pending tool permission awaiting application approval."""

    request_id: str
    turn_id: str
    payload: ToolUsePayload
    tool_names: list[str]


class ChatGatewayModel(Model):
    """
    Tracks turns and pending tool permissions for :class:`ChatGatewayElement`.

    Assistant responses match turns by ``correlation_id`` when present, otherwise
    FIFO. Tool permission requests are keyed by ``request_id`` until approved or
    denied by the outer application.
    """

    on_user_message_submitted = param.Callable(
        default=None,
        doc="``(payload, turn_id)`` when a user message is submitted into the flow.",
    )
    on_assistant_message = param.Callable(
        default=None,
        doc="``(payload, turn_id)`` when an assistant message is linked to a turn.",
    )
    on_tool_event = param.Callable(
        default=None,
        doc="``(event_dict, turn_id)`` when streaming tool calls complete.",
    )
    on_tool_use = param.Callable(
        default=None,
        doc="``(payload, turn_id)`` when a ToolUsePayload arrives at the gateway.",
    )
    on_permission_request = param.Callable(
        default=None,
        doc="``(request_dict, turn_id)`` when tools require user approval.",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._turn_counter = 0
        self._permission_counter = 0
        self._pending_turn_ids: list[str] = []
        self._turn_states: dict[str, TurnState] = {}
        self._permission_requests: dict[str, PermissionRequestState] = {}

    def get_turn_state(self, turn_id: str) -> TurnState | None:
        """Return runtime state for a turn, if it exists."""
        return self._turn_states.get(turn_id)

    def create_turn_id(self) -> str:
        """Generate a unique turn identifier."""
        self._turn_counter += 1
        return f"turn-{self._turn_counter}"

    def create_permission_request_id(self) -> str:
        """Generate a unique permission request identifier."""
        self._permission_counter += 1
        return f"perm-{self._permission_counter}"

    def register_turn(self, turn_id: str, user_message: MessagePayload) -> TurnState:
        """Register a new pending turn."""
        state = TurnState(turn_id=turn_id, user_message=user_message)
        self._turn_states[turn_id] = state
        self._pending_turn_ids.append(turn_id)
        return state

    def match_turn(self, assistant_message: MessagePayload) -> str | None:
        """
        Bind an assistant payload to the oldest pending turn.

        Returns
        -------
        str or None
            The matched turn id, or None if no pending turn exists.
        """
        correlation_id = getattr(assistant_message.model, "correlation_id", None)
        if correlation_id and correlation_id in self._turn_states:
            turn_id = correlation_id
            if turn_id in self._pending_turn_ids:
                self._pending_turn_ids.remove(turn_id)
        elif self._pending_turn_ids:
            turn_id = self._pending_turn_ids.pop(0)
        else:
            assistant_message.model.cancel()
            return None

        state = self._turn_states.get(turn_id)
        if state is None or state.cancelled:
            assistant_message.model.cancel()
            return None

        state.assistant_message = assistant_message
        state.assistant_event.set()
        return turn_id

    def resolve_turn_id_for_tools(self, payload: ToolUsePayload) -> str | None:
        """
        Resolve the turn associated with a tool use payload.

        Uses ``correlation_id`` on the payload model when set; otherwise prefers the
        newest active (non-done, non-cancelled) turn.
        """
        correlation_id = getattr(payload.model, "correlation_id", None) or payload.model.turn_id
        if correlation_id and correlation_id in self._turn_states:
            return correlation_id

        active_ids = [
            tid
            for tid in self._turn_states
            if not self._turn_states[tid].cancelled and not self._turn_states[tid].done
        ]
        if active_ids:
            return active_ids[-1]
        if self._pending_turn_ids:
            return self._pending_turn_ids[-1]
        return None

    @staticmethod
    def tools_need_permission(payload: ToolUsePayload) -> bool:
        """Return True if any tool still requires approval before execution."""
        return payload.model.needs_permission()

    @staticmethod
    def pending_permission_tool_names(payload: ToolUsePayload) -> list[str]:
        """Tool names that are awaiting permission."""
        return payload.model.pending_permission_tool_names()

    def register_permission_request(
        self,
        turn_id: str,
        payload: ToolUsePayload,
    ) -> PermissionRequestState:
        """Store a pending permission request and return its state."""
        request_id = self.create_permission_request_id()
        payload.model.apply_permission_request(request_id)
        state = PermissionRequestState(
            request_id=request_id,
            turn_id=turn_id,
            payload=payload,
            tool_names=self.pending_permission_tool_names(payload),
        )
        self._permission_requests[request_id] = state
        return state

    def get_permission_request(self, request_id: str) -> PermissionRequestState | None:
        """Return a pending permission request, if it exists."""
        return self._permission_requests.get(request_id)

    def pop_permission_request(self, request_id: str) -> PermissionRequestState | None:
        """Remove and return a pending permission request."""
        return self._permission_requests.pop(request_id, None)

    def build_permission_request_event(self, state: PermissionRequestState) -> dict[str, Any]:
        """Build a hook-friendly dict describing a permission request."""
        tools = []
        for record in state.payload.model.tool_uses.values():
            if record.get("status") != "awaiting_permission":
                continue
            tools.append(
                {
                    "name": record.get("model_tool_name"),
                    "adapter_name": record.get("adapter_name"),
                    "provider_name": record.get("provider_name"),
                    "tool_name": record.get("tool_name"),
                    "description": record.get("description"),
                    "parameters": record.get("parameters"),
                }
            )
        return {
            "request_id": state.request_id,
            "turn_id": state.turn_id,
            "tools": tools,
        }

    async def wait_for_assistant(self, turn_id: str) -> MessagePayload:
        """Wait until the assistant message for a turn is linked."""
        state = self._turn_states.get(turn_id)
        if state is None:
            raise KeyError(f"Unknown turn id: {turn_id}")
        if state.cancelled:
            raise RuntimeError(f"Turn {turn_id} was cancelled")
        if state.assistant_message is not None:
            return state.assistant_message
        await state.assistant_event.wait()
        if state.cancelled or state.assistant_message is None:
            raise RuntimeError(f"Turn {turn_id} was cancelled")
        return state.assistant_message

    def is_turn_cancelled(self, turn_id: str) -> bool:
        """Return whether a turn has been cancelled."""
        state = self._turn_states.get(turn_id)
        return state is not None and state.cancelled

    def cancel_turn(self, turn_id: str) -> None:
        """Cancel a turn and its assistant stream if already linked."""
        state = self._turn_states.get(turn_id)
        if state is None:
            return
        state.cancelled = True
        state.done = True
        if turn_id in self._pending_turn_ids:
            self._pending_turn_ids.remove(turn_id)
        if state.assistant_message is not None:
            state.assistant_message.model.cancel()
        state.assistant_event.set()

    def complete_turn(self, turn_id: str) -> None:
        """Mark a turn as completed."""
        state = self._turn_states.get(turn_id)
        if state is not None:
            state.done = True
