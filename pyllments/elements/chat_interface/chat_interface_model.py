from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.tool_use import ToolUsePayload


@dataclass
class PendingToolUseState:
    """Pending tool-use review awaiting a Panel user decision."""

    payload: ToolUsePayload
    review: dict[str, Any]
    pending_indices: list[int]


class ChatInterfaceModel(Model):
    # TODO: Implement batch interface for messages - populating message_list > iterating
    message_list = param.List(instantiate=True, item_type=(MessagePayload, ToolUsePayload))
    persist = param.Boolean(default=False, instantiate=True)

    def __init__(self, **params):
        super().__init__(**params)
        self._branch_counter = 0
        self._execution_owner: str | None = None
        self._superseded_owners: set[str] = set()
        self._pending_tool_uses: list[PendingToolUseState] = []

    async def add_message(
        self,
        payload: MessagePayload | ToolUsePayload,
        *,
        await_tool_ready: bool = False,
    ):
        """
        Centralized handler for new messages and tool use payloads.
        """
        if self.has_message(payload):
            self.param.trigger('message_list')
            return

        if isinstance(payload, MessagePayload):
            if payload.model.mode == 'stream' and not payload.model.streamed:
                await payload.model.stream()
            elif payload.model.mode == 'atomic':
                try:
                    await payload.model.aget_message()
                except AttributeError:
                    pass
        elif isinstance(payload, ToolUsePayload) and await_tool_ready:
            await payload.model.await_ready()

        self.message_list.append(payload)
        self.param.trigger('message_list')

    def has_message(self, payload: MessagePayload | ToolUsePayload) -> bool:
        """Return whether the exact payload object is already displayed."""
        return any(existing is payload for existing in self.message_list)

    def refresh_payload(self, payload: MessagePayload | ToolUsePayload):
        """Notify views that an already displayed payload changed in place."""
        if self.has_message(payload):
            self.param.trigger('message_list')

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

    def is_execution_owner_active(self, owner: str | None) -> bool:
        """Return whether tool results for an owner should enter the active flow."""
        if not owner:
            return True
        if owner in self._superseded_owners:
            return False
        return owner == self._execution_owner

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

    def find_pending_tool_use(self, payload: ToolUsePayload) -> PendingToolUseState | None:
        """Return a pending tool review by payload identity, if one exists."""
        for state in self._pending_tool_uses:
            if state.payload is payload:
                return state
        return None

    def pop_pending_tool_use(self, payload: ToolUsePayload) -> PendingToolUseState | None:
        """Remove and return a pending tool review by payload identity."""
        for index, state in enumerate(self._pending_tool_uses):
            if state.payload is payload:
                return self._pending_tool_uses.pop(index)
        return None

    def pop_all_pending_tool_uses(self) -> list[PendingToolUseState]:
        """Remove and return all pending tool reviews."""
        states = list(self._pending_tool_uses)
        self._pending_tool_uses.clear()
        return states
