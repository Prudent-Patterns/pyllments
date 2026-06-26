"""
Port lifecycle hooks for host-application integration.

Hooks observe payload flow through ports; pack/unpack callbacks define element
behavior.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from loguru import logger as _logger

from pyllments.runtime.scheduler import schedule_task

logger = _logger.bind(name=__name__)

PortEventType = Literal[
    "received",
    "processed",
    "before_emit",
    "emitted",
    "delivered",
    "error",
]
PortDirection = Literal["input", "output"]
HookMode = Literal["await", "schedule"]
HookErrorMode = Literal["raise", "log"]
HookCallback = Callable[["PortEvent"], Any | Awaitable[Any]]


@dataclass
class PortEvent:
    """Runtime context passed to port lifecycle hooks."""

    event: PortEventType
    element_name: str
    port_name: str
    direction: PortDirection
    payload: Any | None = None
    source_port_name: str | None = None
    target_port_name: str | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortHooks:
    """Optional callbacks for observing a port's payload lifecycle."""

    on_received: HookCallback | None = None
    on_processed: HookCallback | None = None
    before_emit: HookCallback | None = None
    on_emitted: HookCallback | None = None
    on_delivered: HookCallback | None = None
    on_error: HookCallback | None = None


@dataclass
class HookPolicy:
    """Execution policy for port lifecycle hooks."""

    mode: HookMode = "await"
    on_error: HookErrorMode = "raise"


def _callback_for_event(hooks: PortHooks | None, event: PortEventType) -> HookCallback | None:
    """Resolve the hook callback for a lifecycle event name."""
    if hooks is None:
        return None
    return {
        "received": hooks.on_received,
        "processed": hooks.on_processed,
        "before_emit": hooks.before_emit,
        "emitted": hooks.on_emitted,
        "delivered": hooks.on_delivered,
        "error": hooks.on_error,
    }.get(event)


async def invoke_port_hook(
    callback: HookCallback | None,
    event: PortEvent,
    policy: HookPolicy | None = None,
) -> None:
    """Invoke a port hook according to the configured policy."""
    if callback is None:
        return

    resolved_policy = policy or HookPolicy()

    async def _run_callback() -> None:
        result = callback(event)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            await result

    if resolved_policy.mode == "schedule":
        task = schedule_task(_run_callback())
        task.add_done_callback(
            lambda completed_task: _handle_scheduled_hook_result(
                completed_task,
                event,
                resolved_policy,
            )
        )
        return

    try:
        await _run_callback()
    except Exception as exc:
        if resolved_policy.on_error == "log":
            logger.opt(exception=exc).warning(
                "Port hook failed for {}.{} event={}",
                event.element_name,
                event.port_name,
                event.event,
            )
            return
        raise


async def fire_port_hook(
    hooks: PortHooks | None,
    event: PortEvent,
    policy: HookPolicy | None = None,
) -> None:
    """Fire the hook registered for ``event.event`` on ``hooks``."""
    await invoke_port_hook(_callback_for_event(hooks, event.event), event, policy)


def resolve_hook_policy(port, default: HookPolicy | None = None) -> HookPolicy:
    """Resolve hook policy from the port's containing element, or use default."""
    element = getattr(port, "containing_element", None)
    if element is not None:
        policy = getattr(element, "hook_policy", None)
        if isinstance(policy, HookPolicy):
            return policy
    return default or HookPolicy()


def element_name_for_port(port) -> str:
    """Best-effort element name for hook events."""
    element = getattr(port, "containing_element", None)
    if element is not None:
        return getattr(element, "name", type(element).__name__)
    return ""


def _handle_scheduled_hook_result(
    task: asyncio.Task,
    event: PortEvent,
    policy: HookPolicy,
) -> None:
    """Handle exceptions raised by scheduled hooks."""
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        if policy.on_error == "log":
            logger.opt(exception=exc).warning(
                "Scheduled port hook failed for {}.{} event={}",
                event.element_name,
                event.port_name,
                event.event,
            )
            return
        logger.opt(exception=exc).error(
            "Scheduled port hook failed for {}.{} event={}",
            event.element_name,
            event.port_name,
            event.event,
        )
