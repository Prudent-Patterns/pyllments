from typing import Any
import asyncio

import param

from pyllments.base.element_base import Element
from loguru import logger
from pyllments.common.loop_registry import LoopRegistry


class PipeElement(Element):
    """
    Element used to test the inputs and outputs of other elements.
    When set up as an input element, it will store the received payloads in a list.
    When set up as an output element, it will emit the the specified payload with send_payload
    
    ports:
        input:
            pipe_input
        output:
            pipe_output
    """
    receive_callback = param.Callable(default=lambda x: x, doc="""
        Callback function for inspecting received payloads. 
        Used with logger.info(), so it should return a printable object.""")
    received_payloads = param.List(default=[], doc="""
        List of received payloads.
        """)
    store_received_payloads = param.Boolean(default=True, doc="""
        Whether to store received payloads.
        """)

    def __init__(self, **params):
        super().__init__(**params)
        self._setup_ports()

    def _setup_ports(self):
        async def unpack(payload: Any):
            """Store the received payload and handle async/sync receive_callback."""
            if self.store_received_payloads:
                self.received_payloads.append(payload)
            if self.receive_callback:
                result = self.receive_callback(payload)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    awaited_result = await result
                    logger.info(f"Unpacking: {awaited_result}")
                else:
                    logger.info(f"Unpacking: {result}")

        self.ports.add_input(
            name='pipe_input',
            unpack_payload_callback=unpack
        )

        async def pack(payload: Any) -> Any:
            """Return the stored output payload (async for consistency)."""
            return payload
        # Setup output port@
        self.ports.add_output(
            name='pipe_output',
            pack_payload_callback=pack
        )

    def clear_received_payloads(self):
        """Clear the list of received payloads"""
        self.received_payloads = []

    def send_payload(self, payload: Any):
        """Synchronously schedules the async stage_emit coroutine."""
        loop = LoopRegistry.get_loop()
        coro = self.ports.output['pipe_output'].stage_emit(payload=payload)
        # Schedule the coroutine to run on the loop, but don't wait here.
        loop.create_task(coro)