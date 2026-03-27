import asyncio

from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload
from pyllments.runtime.loop_registry import LoopRegistry

def test_port_connection():
    """
    Connects the output port of one element to the input port of another
    and tests whether the connected elements in each port are indeed connected
    """
    el1 = Element()
    el2 = Element()

    async def pack(payload: Payload) -> Payload:
        return payload
    async def unpack(payload: Payload):
        return None

    el1.ports.add_output(name='some_output', payload_type=Payload, pack_payload_callback=pack)
    el2.ports.add_input(name='some_input', payload_type=Payload, unpack_payload_callback=unpack)

    el1.ports.output['some_output'] > el2.ports.input['some_input']
    LoopRegistry.get_loop().run_until_complete(asyncio.sleep(0))

    assert el1.ports.output['some_output'].connected_elements[0] is el2
    assert el2.ports.input['some_input'].connected_elements[0] is el1
    LoopRegistry.get_loop().run_until_complete(el1.ports.output['some_output'].close())