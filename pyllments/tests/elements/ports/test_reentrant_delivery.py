"""A cycle back into the port that is still processing is reported, not waited on."""

import pytest

from pyllments.base.element_base import Element
from pyllments.payloads import StructuredPayload
from pyllments.ports.ports import ReentrantDeliveryError


class Relay(Element):
    """Two doors in, one door out. ``loop_input`` re-emits; ``quiet_input`` only records."""

    def __init__(self, **params):
        super().__init__(**params)
        self.seen: list[tuple[str, int]] = []

        async def loop(payload: StructuredPayload):
            self.seen.append(("loop", payload.model.data))
            await self.ports.output["out"].stage_emit(payload=StructuredPayload(data=payload.model.data + 1))

        async def quiet(payload: StructuredPayload):
            self.seen.append(("quiet", payload.model.data))

        async def pack(payload: StructuredPayload) -> StructuredPayload:
            return payload

        self.ports.add_input(name="loop_input", unpack_payload_callback=loop)
        self.ports.add_input(name="quiet_input", unpack_payload_callback=quiet)
        self.ports.add_output(name="out", pack_payload_callback=pack)


@pytest.mark.asyncio
async def test_cycle_through_one_port_raises_instead_of_hanging():
    relay = Relay()
    relay.ports.output["out"] > relay.ports.input["loop_input"]

    # The output port is the first to see its own payload come back, so it reports.
    with pytest.raises(ReentrantDeliveryError, match="port 'out' received"):
        await relay.ports.output["out"].stage_emit(payload=StructuredPayload(data=0))


@pytest.mark.asyncio
async def test_cycle_through_another_door_is_ordinary():
    relay = Relay()
    relay.ports.output["out"] > relay.ports.input["quiet_input"]

    await relay.ports.output["out"].stage_emit(payload=StructuredPayload(data=0))
    assert relay.seen == [("quiet", 0)]

    # The loop door still works when what it emits lands on the quiet door.
    await relay.ports.input["loop_input"].receive(StructuredPayload(data=5), relay.ports.output["out"])
    assert relay.seen == [("quiet", 0), ("loop", 5), ("quiet", 6)]
