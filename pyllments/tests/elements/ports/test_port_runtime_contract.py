from __future__ import annotations

import asyncio

import pytest

from pyllments.base.element_base import Element
from pyllments.runtime.lifecycle_manager import LifecycleManager, manager as lifecycle_manager
from pyllments.runtime.loop_registry import LoopRegistry


def test_output_port_delivery_preserves_connection_order():
    loop = LoopRegistry.get_loop()
    sender = Element(name="sender")
    receiver = Element(name="receiver")

    seen = []

    async def pack(payload: int) -> int:
        return payload

    def unpack_a(payload: int):
        seen.append(("a", payload))

    def unpack_b(payload: int):
        seen.append(("b", payload))

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    in_a = receiver.ports.add_input(name="in_a", unpack_payload_callback=unpack_a, payload_type=int)
    in_b = receiver.ports.add_input(name="in_b", unpack_payload_callback=unpack_b, payload_type=int)

    out.connect([in_a, in_b])
    loop.run_until_complete(out.stage_emit(payload=7))

    assert seen == [("a", 7), ("b", 7)]
    loop.run_until_complete(out.close())


def test_port_inference_resolves_deferred_annotations():
    loop = LoopRegistry.get_loop()
    sender = Element(name="sender3")
    receiver = Element(name="receiver3")

    seen = []

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        seen.append(payload)

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    inn = receiver.ports.add_input(name="in", unpack_payload_callback=unpack)

    assert out.required_items["payload"]["type"] is int
    assert out.payload_type is int
    assert inn.payload_type is int

    out.connect(inn)
    loop.run_until_complete(out.stage_emit(payload=3))

    assert seen == [3]
    loop.run_until_complete(out.close())


def test_sequential_stage_emit_delivers_in_order():
    loop = LoopRegistry.get_loop()
    sender = Element(name="sender2")
    receiver = Element(name="receiver2")

    seen = []

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        seen.append(payload)

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    inn = receiver.ports.add_input(name="in", unpack_payload_callback=unpack, payload_type=int)

    out.connect(inn)
    loop.run_until_complete(out.stage_emit(payload=1))
    loop.run_until_complete(out.stage_emit(payload=2))

    assert seen == [1, 2]
    loop.run_until_complete(out.close())


def test_lifecycle_shutdown_closes_registered_resources():
    loop = LoopRegistry.get_loop()
    LifecycleManager.reset_for_tests()

    class DummyResource:
        def __init__(self):
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1
            await asyncio.sleep(0)

    resource = DummyResource()
    lifecycle_manager.register_resource(resource)

    loop.run_until_complete(lifecycle_manager.shutdown())
    loop.run_until_complete(lifecycle_manager.shutdown())

    assert resource.close_calls == 1


def test_latched_output_replays_to_late_connection():
    loop = LoopRegistry.get_loop()
    sender = Element(name="latched_sender")
    receiver = Element(name="latched_receiver")

    seen = []

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        seen.append(payload)

    out = sender.ports.add_output(name="out", pack_payload_callback=pack, latched=True)
    inn = receiver.ports.add_input(name="in", unpack_payload_callback=unpack, payload_type=int)

    loop.run_until_complete(out.stage_emit(payload=42))
    out.connect(inn)
    loop.run_until_complete(asyncio.sleep(0))

    assert seen == [42]
    loop.run_until_complete(out.close())


@pytest.mark.asyncio
async def test_connect_is_synchronous_in_async_context():
    sender = Element(name="async_sender")
    receiver = Element(name="async_receiver")

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        pass

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    inn = receiver.ports.add_input(name="in", unpack_payload_callback=unpack, payload_type=int)
    out.connect(inn)
    assert out.connected_elements[0] is receiver
