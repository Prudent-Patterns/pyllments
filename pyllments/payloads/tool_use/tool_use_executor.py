from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .tool_use_payload import ToolUsePayload


class ToolUseExecutorNotBoundError(RuntimeError):
    """Raised when a ToolUsePayload attempts execution without a bound executor."""


class ToolUseExecutor(Protocol):
    """Runtime executor contract for ToolUsePayload delegation."""

    async def execute_tool_use_payload(
        self,
        payload: ToolUsePayload,
        tool_call_indices: list[int] | None = None,
    ) -> ToolUsePayload: ...
