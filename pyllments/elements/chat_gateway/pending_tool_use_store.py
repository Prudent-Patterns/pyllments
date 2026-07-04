"""
Storage-neutral contract for pending tool permission snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class PendingToolUseSnapshot:
    """Serialized pending permission request for one ToolUsePayload."""

    payload_data: dict[str, Any]
    created_at: float
    updated_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


class PendingToolUseStore(Protocol):
    """Application-owned persistence for gateway pending tool permission state."""

    async def load_pending_tool_uses(self) -> list[PendingToolUseSnapshot]: ...

    async def save_pending_tool_use(
        self, snapshot: PendingToolUseSnapshot
    ) -> PendingToolUseSnapshot: ...

    async def clear_pending_tool_use(self, snapshot: PendingToolUseSnapshot) -> None: ...
