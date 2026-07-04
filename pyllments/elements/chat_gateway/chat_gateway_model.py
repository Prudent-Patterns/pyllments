from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
class PendingToolUseState:
    """Pending tool-use review awaiting application policy decisions."""

    payload: ToolUsePayload
    review: dict[str, Any]
    pending_indices: list[int]
    pending_snapshot: Any = None


class ChatGatewayModel(Model):
    """
    Tracks turns and pending tool reviews for :class:`ChatGatewayElement`.

    Assistant responses match turns in FIFO order. Tool reviews are held until
    the outer application acknowledges or returns policy decisions.
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
        doc="``(event_dict)`` when streaming tool calls complete.",
    )
    on_tool_use = param.Callable(
        default=None,
        doc=(
            "``(review) -> response | None`` when a ToolUsePayload arrives. "
            "Return None to acknowledge non-permission tools, or return decisions "
            "for pending permission tools."
        ),
    )
    on_tool_result = param.Callable(
        default=None,
        doc="``(result_notice)`` when a completed ToolUsePayload returns to the gateway.",
    )
    on_pending_tool_use_restored = param.Callable(
        default=None,
        doc="``(review)`` when pending tool reviews are hydrated on startup.",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._turn_counter = 0
        self._branch_counter = 0
        self._execution_owner: str | None = None
        self._superseded_owners: set[str] = set()
        self._pending_turn_ids: list[str] = []
        self._turn_states: dict[str, TurnState] = {}
        self._pending_tool_uses: list[PendingToolUseState] = []

    def begin_new_execution_branch(self) -> tuple[str | None, str]:
        """
        Start a new execution branch and supersede the previous one.

        Returns
        -------
        tuple[str | None, str]
            Previous owner (if any) and the new active owner token.
        """
        previous = self._execution_owner
        self._branch_counter += 1
        self._execution_owner = f"branch-{self._branch_counter}"
        if previous:
            self._superseded_owners.add(previous)
        return previous, self._execution_owner

    def current_execution_owner(self) -> str:
        """Return the active execution owner, creating one when needed."""
        if self._execution_owner is None:
            self._branch_counter += 1
            self._execution_owner = f"branch-{self._branch_counter}"
        return self._execution_owner

    def supersede_owner(self, owner: str | None) -> None:
        """Mark an execution owner inactive without starting a new branch."""
        if owner:
            self._superseded_owners.add(owner)

    def is_execution_owner_active(self, owner: str | None) -> bool:
        """Return whether tool results for an owner should enter the active flow."""
        if not owner:
            return True
        if owner in self._superseded_owners:
            return False
        return owner == self._execution_owner

    def get_turn_state(self, turn_id: str) -> TurnState | None:
        """Return runtime state for a turn, if it exists."""
        return self._turn_states.get(turn_id)

    def create_turn_id(self) -> str:
        """Generate a unique turn identifier."""
        self._turn_counter += 1
        return f"turn-{self._turn_counter}"

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
        if self._pending_turn_ids:
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

        Prefers the newest active (non-done, non-cancelled) turn.
        """
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

    def register_pending_tool_use(
        self,
        payload: ToolUsePayload,
        review: dict[str, Any],
        pending_indices: list[int] | None = None,
    ) -> PendingToolUseState:
        """Store a pending tool review and return its state."""
        indices = pending_indices or payload.model.pending_permission_indices()
        payload.model.apply_permission_request(indices)
        state = PendingToolUseState(
            payload=payload,
            review=review,
            pending_indices=indices,
        )
        self._pending_tool_uses.append(state)
        return state

    def get_pending_tool_use(self, review: dict[str, Any]) -> PendingToolUseState | None:
        """Return a pending tool review, if it exists."""
        for state in self._pending_tool_uses:
            if state.review is review:
                return state
        return None

    def pop_pending_tool_use(self, review: dict[str, Any]) -> PendingToolUseState | None:
        """Remove and return a pending tool review."""
        for index, state in enumerate(self._pending_tool_uses):
            if state.review is review:
                return self._pending_tool_uses.pop(index)
        return None

    def pop_all_pending_tool_uses(self) -> list[PendingToolUseState]:
        """Remove and return all pending tool reviews."""
        states = list(self._pending_tool_uses)
        self._pending_tool_uses.clear()
        return states

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
