from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jinja2
import param

from pyllments.base.model_base import Model

if TYPE_CHECKING:
    from pyllments.payloads import MessagePayload, ToolUsePayload


DEFAULT_TURN_NOTICE = (
    "Tool round {{ round }} of {{ max_rounds }}; failed calls {{ failures }} of "
    "{{ max_failures }}.\n"
    "{% if tools_allowed %}After the last round, answer the person in words with what "
    "you have.{% else %}Tools are off for this reply: answer the person in words now."
    "{% endif %}"
)


@dataclass
class TurnState:
    """
    Per-turn runtime state (not exposed via Param).

    A turn is one user message and the rounds that answer it: an assistant
    reply, then, when that reply called tools, the results of those calls,
    then the next reply. ``assistant_messages[i]`` is round ``i``'s reply and
    ``tool_results[i]`` its results. The turn is done when a reply calls no
    tools, is cancelled, or fails.
    """

    turn_id: str
    user_message: MessagePayload
    assistant_messages: list = field(default_factory=list)
    tool_results: list = field(default_factory=list)
    replies_emitted: set = field(default_factory=set)
    failed_calls: int = 0
    facts: dict = field(default_factory=dict)
    cancelled: bool = False
    done: bool = False
    error: str | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def assistant_message(self) -> MessagePayload | None:
        return self.assistant_messages[-1] if self.assistant_messages else None

    @property
    def rounds(self) -> int:
        return len(self.assistant_messages)

    @property
    def open(self) -> bool:
        return not self.done and not self.cancelled

    def notify(self) -> None:
        self.changed.set()


@dataclass
class PendingToolUseState:
    """Pending tool-use review awaiting application policy decisions."""

    payload: ToolUsePayload
    review: dict[str, Any]
    pending_indices: list[int]
    pending_snapshot: Any = None


def _assistant_finished(message: MessagePayload) -> bool:
    return message.finished


class ChatGatewayModel(Model):
    """
    Tracks turns and pending tool reviews for :class:`ChatGatewayElement`.

    An assistant reply joins the open turn whose last reply called tools and
    has its results back; otherwise it matches the oldest pending turn in FIFO
    order. Tool reviews are held until the outer application acknowledges or
    returns policy decisions.
    """

    max_tool_rounds = param.Integer(
        default=6,
        bounds=(0, None),
        doc=(
            "How many replies in one turn may run tools. The reply after the last "
            "allowed one has its calls denied with a reason the model can read; a "
            "further reply that still calls tools fails the turn."
        ),
    )

    max_tool_failures = param.Integer(
        default=3,
        bounds=(0, None),
        doc=(
            "How many tool calls may fail in one turn before the next reply is made "
            "without tools, so the model answers with what it has and says what failed."
        ),
    )

    turn_notice_template = param.String(
        default=DEFAULT_TURN_NOTICE,
        doc=(
            "Jinja2 for the system message emitted on ``turn_notice_output`` as the "
            "last arrival of every round. Variables: ``round`` (the reply about to be made, 1-based), "
            "``max_rounds``, ``failures``, ``max_failures``, ``tools_allowed`` "
            "(False when this reply is made without tools), plus the ``facts`` "
            "given at submit time, such as today's date."
        ),
    )

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

    def register_turn(
        self, turn_id: str, user_message: MessagePayload, facts: dict | None = None
    ) -> TurnState:
        """Register a new pending turn; ``facts`` feed its turn notices."""
        state = TurnState(turn_id=turn_id, user_message=user_message, facts=dict(facts or {}))
        self._turn_states[turn_id] = state
        self._pending_turn_ids.append(turn_id)
        return state

    def _turn_awaiting_next_round(self) -> TurnState | None:
        """The newest open turn whose last reply called tools and has its results back."""
        for turn_id in reversed(list(self._turn_states)):
            state = self._turn_states[turn_id]
            if not state.open or not state.assistant_messages:
                continue
            last = state.assistant_messages[-1]
            if (
                _assistant_finished(last)
                and last.model.tool_calls
                and len(state.tool_results) == state.rounds
            ):
                return state
        return None

    def match_turn(self, assistant_message: MessagePayload) -> str | None:
        """
        Bind an assistant payload to its turn.

        A turn waiting on the reply to its tool results takes it as the next
        round. Otherwise the oldest pending turn takes it as its first.

        Returns
        -------
        str or None
            The matched turn id, or None if no turn can take it.
        """
        continuing = self._turn_awaiting_next_round()
        if continuing is not None:
            continuing.assistant_messages.append(assistant_message)
            continuing.notify()
            return continuing.turn_id

        if self._pending_turn_ids:
            turn_id = self._pending_turn_ids.pop(0)
        else:
            assistant_message.model.cancel()
            return None

        state = self._turn_states.get(turn_id)
        if state is None or state.cancelled:
            assistant_message.model.cancel()
            return None

        state.assistant_messages.append(assistant_message)
        state.notify()
        return turn_id

    def resolve_turn_id_for_tools(self, payload: ToolUsePayload) -> str | None:
        """
        Resolve the turn associated with a tool use payload.

        Prefers the newest active (non-done, non-cancelled) turn.
        """
        active_ids = [tid for tid in self._turn_states if self._turn_states[tid].open]
        if active_ids:
            return active_ids[-1]
        if self._pending_turn_ids:
            return self._pending_turn_ids[-1]
        return None

    def claim_reply_emission(self, turn_id: str, round_index: int) -> MessagePayload | None:
        """
        The reply to emit as finished for a round, once; None if already claimed.

        Two paths can finish a round's reply, the watcher that sees it stream to
        its end and the tool path that receives the calls it made. Whichever is
        first emits; the other finds nothing to do.
        """
        state = self._turn_states.get(turn_id)
        if state is None or state.cancelled or round_index >= len(state.assistant_messages):
            return None
        if round_index in state.replies_emitted:
            return None
        state.replies_emitted.add(round_index)
        return state.assistant_messages[round_index]

    def record_tool_results(self, turn_id: str, payload: ToolUsePayload) -> None:
        """Attach a round's finished tool results to the turn and wake its reader."""
        state = self._turn_states.get(turn_id)
        if state is None:
            return
        state.tool_results.append(payload)
        state.failed_calls += sum(
            1 for record in payload.model.tool_calls if record.get("status") == "failed"
        )
        state.notify()

    def turn_awaits_results(self, turn_id: str | None) -> bool:
        """Has this turn a reply whose tool results have not come back yet?"""
        state = self._turn_states.get(turn_id or "")
        return bool(state and state.open and state.rounds > len(state.tool_results))

    def turn_notice_facts(self, turn_id: str) -> dict[str, Any]:
        """The state of the turn as the model should know it before its next reply."""
        state = self._turn_states.get(turn_id)
        if state is None:
            return {}
        return {
            **state.facts,
            "round": state.rounds + 1,
            "max_rounds": self.max_tool_rounds,
            "failures": state.failed_calls,
            "max_failures": self.max_tool_failures,
            "tools_allowed": not self.next_round_is_last(turn_id),
        }

    def render_turn_notice(self, turn_id: str) -> str:
        """``turn_notice_template`` rendered for the next reply of this turn."""
        template = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
            self.turn_notice_template
        )
        return template.render(**self.turn_notice_facts(turn_id)).strip()

    def next_round_is_last(self, turn_id: str) -> bool:
        """After these results, must the next reply be made without tools?"""
        state = self._turn_states.get(turn_id)
        if state is None:
            return False
        return state.rounds >= self.max_tool_rounds or state.failed_calls >= self.max_tool_failures

    def tool_rounds_over_budget(self, turn_id: str) -> str | None:
        """
        Judge a tool request against the round budget.

        Returns ``None`` when the call may run, ``"deny"`` when the budget is
        spent and the model should answer, ``"fail"`` when it kept calling.
        """
        state = self._turn_states.get(turn_id)
        if state is None:
            return None
        over_rounds = state.rounds > self.max_tool_rounds
        over_failures = state.failed_calls >= self.max_tool_failures
        if not over_rounds and not over_failures:
            return None
        # One reply past a spent budget is denied with a reason; the next fails the turn.
        limit = self.max_tool_rounds if over_rounds else state.rounds - 1
        if state.rounds > limit + 1:
            return "fail"
        return "deny"

    def fail_turn(self, turn_id: str, error: str) -> None:
        """End a turn with an error its reader will see."""
        state = self._turn_states.get(turn_id)
        if state is None:
            return
        state.error = error
        self.cancel_turn(turn_id)

    async def _wait_until(self, state: TurnState, ready) -> bool:
        """Wait for ``ready(state)``; False when the turn was cancelled first."""
        while True:
            if state.cancelled:
                return False
            if ready(state):
                return True
            state.changed.clear()
            await state.changed.wait()

    async def wait_for_round(self, turn_id: str, index: int) -> MessagePayload | None:
        """The reply of round ``index``, or None when the turn was cancelled."""
        state = self._turn_states.get(turn_id)
        if state is None:
            raise KeyError(f"Unknown turn id: {turn_id}")
        if await self._wait_until(state, lambda s: len(s.assistant_messages) > index):
            return state.assistant_messages[index]
        return None

    async def wait_for_tool_results(self, turn_id: str, index: int) -> ToolUsePayload | None:
        """The results of round ``index``, or None when the turn was cancelled."""
        state = self._turn_states.get(turn_id)
        if state is None:
            raise KeyError(f"Unknown turn id: {turn_id}")
        if await self._wait_until(state, lambda s: len(s.tool_results) > index):
            return state.tool_results[index]
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
        """Wait until the first assistant message for a turn is linked."""
        message = await self.wait_for_round(turn_id, 0)
        if message is None:
            raise RuntimeError(f"Turn {turn_id} was cancelled")
        return message

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
        state.notify()

    def complete_turn(self, turn_id: str) -> None:
        """Mark a turn as completed."""
        state = self._turn_states.get(turn_id)
        if state is not None:
            state.done = True
            state.notify()
