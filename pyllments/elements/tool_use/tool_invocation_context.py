from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

InterruptPolicy = Literal["cancel", "drain", "detach"]
ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class ToolCancelled(Exception):
    """Raised when a cooperative tool observes an abort signal."""


class AbortSignal:
    """Cooperative cancellation signal shared with an in-flight tool invocation."""

    def __init__(self):
        self._cancelled = False
        self._event = asyncio.Event()

    def cancel(self) -> None:
        """Request cancellation of the associated tool invocation."""
        if self._cancelled:
            return
        self._cancelled = True
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._cancelled

    async def wait_cancelled(self) -> None:
        """Block until cancellation is requested."""
        await self._event.wait()


@dataclass
class ToolInvocationContext:
    """
    Runtime wrapper for one executing tool call.

    Exists only while ToolUseElement is running the call. Tools opt in by
    accepting an injected ``context`` parameter; simple tools ignore it.
    """

    tool_call_index: int
    execution_owner: str
    abort_signal: AbortSignal = field(default_factory=AbortSignal)
    interrupt_policy: InterruptPolicy = "drain"
    _progress_callback: ProgressCallback | None = field(default=None, repr=False)

    def is_active(self) -> bool:
        """Return whether cancellation has not been requested."""
        return not self.abort_signal.is_cancelled()

    def throw_if_cancelled(self) -> None:
        """Raise :class:`ToolCancelled` when cancellation was requested."""
        if self.abort_signal.is_cancelled():
            raise ToolCancelled("Tool invocation was cancelled")

    async def report_progress(self, event: dict[str, Any]) -> None:
        """Emit a progress event for application/UI observers."""
        if self._progress_callback is None:
            return
        result = self._progress_callback(event)
        if asyncio.iscoroutine(result):
            await result
