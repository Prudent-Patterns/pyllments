"""Explicit background task scheduling for Pyllments runtime code."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from pyllments.runtime.loop_registry import LoopRegistry

T = TypeVar("T")


def resolve_loop() -> asyncio.AbstractEventLoop:
    """
    Resolve the active event loop for scheduling.

    Prefers the currently running loop; falls back to the bound runtime loop
    when Pyllments owns a headless or test runtime.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return LoopRegistry.get_loop()


def schedule_task(coro: Coroutine[Any, Any, T], *, name: str | None = None) -> asyncio.Task[T]:
    """
    Schedule a coroutine on the active runtime loop without blocking the caller.

    Use this for explicit fire-and-forget work. Normal port ``emit()`` paths
    should remain awaited for deterministic delivery.
    """
    loop = resolve_loop()
    return loop.create_task(coro, name=name)
