from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pyllments.base.model_base import Model

if TYPE_CHECKING:
    from pyllments.payloads import MessagePayload


@dataclass
class TurnState:
    """Per-turn runtime state (not exposed via Param)."""

    turn_id: str
    user_message: MessagePayload
    assistant_message: MessagePayload | None = None
    cancelled: bool = False
    done: bool = False
    assistant_event: asyncio.Event = field(default_factory=asyncio.Event)


class ChatGatewayModel(Model):
    """
    Tracks pending and active turns for :class:`ChatGatewayElement`.

    Phase 1 matches assistant responses to turns using FIFO ordering.
    Turn registry state is private; only element-level params are user-facing.
    """

    def __init__(self, **params):
        super().__init__(**params)
        self._turn_counter = 0
        self._pending_turn_ids: list[str] = []
        self._turn_states: dict[str, TurnState] = {}

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
        correlation_id = getattr(assistant_message.model, 'correlation_id', None)
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
