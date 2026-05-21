from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


MessageStreamEventType = Literal[
    "token",
    "tool_call_delta",
    "tool_calls_complete",
    "done",
    "cancelled",
    "error",
]


@dataclass(frozen=True)
class MessageStreamEvent:
    """
    Provider-neutral streaming event emitted while consuming a message stream.
    """

    type: MessageStreamEventType
    content_delta: str | None = None
    tool_call_delta: dict | None = None
    tool_calls: list[dict] | None = None
    raw: Any | None = None
    error: str | None = None
