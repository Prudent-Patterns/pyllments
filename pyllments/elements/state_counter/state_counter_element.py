from __future__ import annotations

import asyncio
from typing import Any, Callable, Union

import param

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.elements.flow_control import FlowController
from pyllments.payloads.structured import StructuredPayload
from pyllments.runtime.loop_registry import LoopRegistry


def _default_reset_predicate(_payload: Any, _state: dict[str, Any]) -> bool:
    return False


def _default_count_predicate(_payload: Any, _state: dict[str, Any]) -> bool:
    return False


def _default_delta_fn(_payload: Any, _state: dict[str, Any]) -> int:
    return 1


class StateCounterElement(Element):
    """
    Stateful observer element that counts observed payloads and emits structured state.

    Watches arbitrary payloads on reset/count inputs, applies configurable predicates,
    and emits the current counter state as a :class:`StructuredPayload`.

    Ports
    -----
    input
        • **reset_emit_input** (Payload | list[Payload]) – resets when ``reset_predicate`` matches.
        • **count_emit_input** (Payload | list[Payload]) – increments when ``count_predicate`` matches.
    output
        • **state_output** (StructuredPayload) – current counter/budget snapshot.

    Parameters
    ----------
    initial_count : int
        Initial count and the value restored when a reset rule matches.
    limit : int or None
        Optional budget ceiling. When set, ``remaining`` and ``exhausted`` are derived
        from ``limit - count``.
    reset_predicate : callable
        ``(payload, state) -> bool`` deciding whether an observed payload resets.
    count_predicate : callable
        ``(payload, state) -> bool`` deciding whether an observed payload increments.
    delta_fn : callable
        ``(payload, state) -> int`` amount to add when counting.
    on_exhausted : callable, optional
        Called once when ``remaining`` transitions to zero (budget exhausted).
        Receives the emitted state dict. May be sync or async.
    """

    initial_count = param.Integer(default=0, bounds=(0, None), doc="Count restored on reset.")
    limit = param.Integer(default=None, bounds=(0, None), allow_None=True, doc="""
        Optional budget limit used to compute remaining capacity.""")

    reset_predicate = param.Callable(
        default=_default_reset_predicate,
        doc="Predicate deciding whether a payload triggers reset.",
    )
    count_predicate = param.Callable(
        default=_default_count_predicate,
        doc="Predicate deciding whether a payload triggers increment.",
    )
    delta_fn = param.Callable(
        default=_default_delta_fn,
        doc="Function returning the increment amount when counting.",
    )
    on_exhausted = param.Callable(default=None, doc="""
        Optional callback invoked when the budget becomes exhausted.""")

    flow_controller = param.ClassSelector(class_=FlowController, doc="""
        FlowController managing port setup and invocation.""")

    def __init__(self, **params):
        super().__init__(**params)
        self._pending_tasks = set()
        self._flow_controller_setup()
        self.ports = self.flow_controller.ports
        self._ensure_context(self.flow_controller.context)

    def _ensure_context(self, c: dict[str, Any]) -> dict[str, Any]:
        """Initialize FlowController context keys used by the counter."""
        c.setdefault("count", self.initial_count)
        c.setdefault("exhausted_active", self._is_exhausted(c["count"]))
        return c

    def _is_exhausted(self, count: int) -> bool:
        return self.limit is not None and self.limit - count <= 0

    def build_state(
        self,
        c: dict[str, Any] | None = None,
        last_event: str | None = None,
        last_delta: int | None = None,
    ) -> dict[str, Any]:
        """Return a snapshot dict suitable for ``StructuredPayload`` emission."""
        c = self._ensure_context(self.flow_controller.context if c is None else c)
        count = c["count"]
        remaining = None
        exhausted = False
        if self.limit is not None:
            remaining = max(0, self.limit - count)
            exhausted = remaining <= 0

        return {
            "count": count,
            "limit": self.limit,
            "remaining": remaining,
            "exhausted": exhausted,
            "last_event": last_event,
            "last_delta": last_delta,
        }

    def handle_reset(
        self,
        payload: Payload | list[Payload],
        c: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Apply reset when ``reset_predicate`` matches.

        Returns
        -------
        dict or None
            Updated state dict when reset applied, otherwise ``None``.
        """
        c = self._ensure_context(self.flow_controller.context if c is None else c)
        state = self.build_state(c)
        if not self.reset_predicate(payload, state):
            return None

        c["count"] = self.initial_count
        state = self.build_state(c, last_event="reset", last_delta=0)
        c["exhausted_active"] = state["exhausted"]
        return state

    def handle_count(
        self,
        payload: Payload | list[Payload],
        c: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Apply increment when ``count_predicate`` matches.

        Returns
        -------
        dict or None
            Updated state dict when count applied, otherwise ``None``.
        """
        c = self._ensure_context(self.flow_controller.context if c is None else c)
        state = self.build_state(c)
        if not self.count_predicate(payload, state):
            return None

        delta = int(self.delta_fn(payload, state))
        c["count"] += delta
        state = self.build_state(c, last_event="count", last_delta=delta)
        c["exhausted_active"] = state["exhausted"]
        return state

    def _flow_controller_setup(self):
        observed_payload_type = Union[Payload, list[Payload]]
        flow_map = {
            "input": {
                "reset_emit_input": {"payload_type": observed_payload_type},
                "count_emit_input": {"payload_type": observed_payload_type},
            },
            "output": {
                "state_output": {"payload_type": StructuredPayload},
            },
        }

        self.flow_controller = FlowController(
            containing_element=self,
            flow_fn=self._flow_fn_setup(),
            flow_map=flow_map,
            context={},
        )

    def _flow_fn_setup(self) -> Callable:
        def flow_fn(active_input_port, c, **kwargs):
            port_name = active_input_port.name
            payload = active_input_port.payload
            state_output = kwargs["state_output"]

            # FlowController invokes this synchronously. Keep context mutation before
            # scheduling async emission so reset/count transitions are explicit.
            self._ensure_context(c)
            was_exhausted = c["exhausted_active"]
            new_state = None

            if port_name == "reset_emit_input":
                new_state = self.handle_reset(payload, c)
            elif port_name == "count_emit_input":
                new_state = self.handle_count(payload, c)

            if new_state is None:
                return

            self._schedule_task(
                self._emit_state_and_maybe_exhaust(
                    state_output=state_output,
                    new_state=new_state,
                    was_exhausted=was_exhausted,
                )
            )

        return flow_fn

    def _schedule_task(self, coroutine):
        """Track element-local async work without relying on global lifecycle drains."""
        loop = LoopRegistry.get_loop()
        task = loop.create_task(coroutine)
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return task

    async def _emit_state_and_maybe_exhaust(
        self,
        state_output,
        new_state: dict[str, Any],
        was_exhausted: bool,
    ):
        """Emit structured state, then run exhaustion callback when budget hits zero."""
        await state_output.emit(StructuredPayload(data=new_state))

        if (
            self.on_exhausted
            and new_state.get("exhausted")
            and not was_exhausted
        ):
            result = self.on_exhausted(new_state)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result

    async def drain(self):
        """Wait for state-counter emissions and callbacks scheduled by this element."""
        while self._pending_tasks:
            await asyncio.gather(*self._pending_tasks)
        await self.ports.output["state_output"].drain()

    def emit_state(self):
        """Push the current state through ``state_output`` without changing the counter."""
        state = self.build_state(self.flow_controller.context)
        state_output = self.flow_controller.flow_port_map["state_output"]
        self._schedule_task(state_output.emit(StructuredPayload(data=state)))
