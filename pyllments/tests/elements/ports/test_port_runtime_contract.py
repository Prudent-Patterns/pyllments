from __future__ import annotations

import asyncio

from pyllments.base.element_base import Element
from pyllments.runtime.lifecycle_manager import LifecycleManager, manager as lifecycle_manager
from pyllments.runtime.loop_registry import LoopRegistry


def test_output_port_drain_preserves_connection_order():
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

    loop.run_until_complete(out.connect([in_a, in_b]))
    loop.run_until_complete(out.stage_emit(payload=7))
    loop.run_until_complete(out.drain())

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

    loop.run_until_complete(out.connect(inn))
    loop.run_until_complete(out.stage_emit(payload=3))
    loop.run_until_complete(out.drain())

    assert seen == [3]
    loop.run_until_complete(out.close())


def test_lifecycle_manager_drain_flushes_registered_ports():
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

    loop.run_until_complete(out.connect(inn))
    loop.run_until_complete(out.stage_emit(payload=1))
    loop.run_until_complete(out.stage_emit(payload=2))
    loop.run_until_complete(lifecycle_manager.drain())

    assert seen == [1, 2]
    loop.run_until_complete(out.close())


def test_lifecycle_shutdown_idempotent_on_isolated_manager():
    loop = LoopRegistry.get_loop()

    class IsolatedLifecycleManager(LifecycleManager):
        _instance = None
        _initialized = False

    manager = IsolatedLifecycleManager()

    class DummyResource:
        def __init__(self):
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1
            await asyncio.sleep(0)

    resource = DummyResource()
    manager.register_resource(resource)

    loop.run_until_complete(manager.shutdown())
    loop.run_until_complete(manager.shutdown())

    assert resource.close_calls == 1
