from __future__ import annotations

import asyncio

import pytest

from pyllments.base.element_base import Element
from pyllments.elements.context_builder import ContextBuilderElement
from pyllments.payloads import MessagePayload
from pyllments.ports import HookPolicy, PortHooks
from pyllments.runtime.loop_registry import LoopRegistry


def test_input_port_hooks_fire_around_unpack():
    loop = LoopRegistry.get_loop()
    events = []
    sender = Element(name="hook_sender")
    receiver = Element(
        name="hook_receiver",
        port_hooks={
            "in": PortHooks(
                on_received=lambda event: events.append(
                    (event.event, event.payload, event.source_port_name)
                ),
                on_processed=lambda event: events.append((event.event, event.payload)),
            )
        },
    )

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        events.append(("unpack", payload))

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    inn = receiver.ports.add_input(name="in", unpack_payload_callback=unpack)

    try:
        out.connect(inn)
        loop.run_until_complete(out.stage_emit(payload=5))
        loop.run_until_complete(out.drain())

        assert events == [
            ("received", 5, "out"),
            ("unpack", 5),
            ("processed", 5),
        ]
    finally:
        loop.run_until_complete(out.close())


def test_output_port_hooks_fire_around_emit_and_delivery():
    loop = LoopRegistry.get_loop()
    events = []
    sender = Element(
        name="hook_output_sender",
        port_hooks={
            "out": PortHooks(
                before_emit=lambda event: events.append((event.event, event.payload)),
                on_emitted=lambda event: events.append((event.event, event.payload)),
                on_delivered=lambda event: events.append(
                    (event.event, event.target_port_name)
                ),
            )
        },
    )
    receiver = Element(name="hook_output_receiver")

    async def pack(payload: int) -> int:
        return payload

    def unpack_a(payload: int):
        events.append(("in_a", payload))

    def unpack_b(payload: int):
        events.append(("in_b", payload))

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    in_a = receiver.ports.add_input(name="in_a", unpack_payload_callback=unpack_a)
    in_b = receiver.ports.add_input(name="in_b", unpack_payload_callback=unpack_b)

    try:
        out.connect([in_a, in_b])
        loop.run_until_complete(out.stage_emit(payload=7))
        loop.run_until_complete(out.drain())

        assert events == [
            ("before_emit", 7),
            ("in_a", 7),
            ("delivered", "in_a"),
            ("in_b", 7),
            ("delivered", "in_b"),
            ("emitted", 7),
        ]
    finally:
        loop.run_until_complete(out.close())


def test_hooks_support_async_callbacks():
    loop = LoopRegistry.get_loop()
    events = []

    async def on_before_emit(event):
        await asyncio.sleep(0)
        events.append((event.event, event.payload))

    sender = Element(
        name="async_hook_sender",
        port_hooks={"out": PortHooks(before_emit=on_before_emit)},
    )

    async def pack(payload: int) -> int:
        return payload

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)

    try:
        loop.run_until_complete(out.stage_emit(payload=9))
        loop.run_until_complete(out.drain())

        assert events == [("before_emit", 9)]
    finally:
        loop.run_until_complete(out.close())


def test_hook_policy_raise_propagates_inline_hook_errors():
    loop = LoopRegistry.get_loop()

    def fail_before_emit(event):
        raise RuntimeError("hook failed")

    sender = Element(
        name="raise_policy_sender",
        port_hooks={"out": PortHooks(before_emit=fail_before_emit)},
        hook_policy=HookPolicy(on_error="raise"),
    )

    async def pack(payload: int) -> int:
        return payload

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)

    try:
        with pytest.raises(RuntimeError, match="hook failed"):
            loop.run_until_complete(out.stage_emit(payload=1))
    finally:
        loop.run_until_complete(out.close())


def test_hook_policy_log_swallows_inline_hook_errors():
    loop = LoopRegistry.get_loop()

    def fail_before_emit(event):
        raise RuntimeError("hook failed")

    sender = Element(
        name="log_policy_sender",
        port_hooks={"out": PortHooks(before_emit=fail_before_emit)},
        hook_policy=HookPolicy(on_error="log"),
    )

    async def pack(payload: int) -> int:
        return payload

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)

    try:
        loop.run_until_complete(out.stage_emit(payload=2))
        loop.run_until_complete(out.drain())
    finally:
        loop.run_until_complete(out.close())


def test_element_port_hooks_attach_to_flow_controller_generated_ports():
    loop = LoopRegistry.get_loop()
    events = []
    context_builder = ContextBuilderElement(
        input_map={
            "user_message": {
                "payload_type": MessagePayload,
            }
        },
        trigger_map={"user_message": ["user_message"]},
        port_hooks={
            "user_message": PortHooks(
                on_received=lambda event: events.append(
                    (event.event, event.port_name, event.element_name)
                )
            )
        },
    )
    sender = Element(name="flow_hook_sender")

    async def pack(payload: MessagePayload) -> MessagePayload:
        return payload

    out = sender.ports.add_output(name="message_output", pack_payload_callback=pack)

    try:
        out.connect(context_builder.ports.input["user_message"])
        loop.run_until_complete(out.stage_emit(payload=MessagePayload(content="hello")))
        loop.run_until_complete(out.drain())

        assert events == [
            ("received", "user_message", context_builder.name),
        ]
    finally:
        loop.run_until_complete(out.close())
        for output_port in context_builder.ports.output.values():
            loop.run_until_complete(output_port.close())
