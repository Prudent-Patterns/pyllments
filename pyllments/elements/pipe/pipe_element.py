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
        # internal future for send_and_receive to await incoming payload
        self._receive_future = None
        self._setup_ports()

    def _setup_ports(self):
        async def unpack(payload: Any):
            """Store the received payload and handle async/sync receive_callback."""
            # conditionally store payload history
            if getattr(self, 'store_received_payloads', False):
                self.received_payloads.append(payload)
            if self.receive_callback:
                result = self.receive_callback(payload)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    awaited_result = await result
                    logger.info(f"Unpacking: {awaited_result}")
                else:
                    logger.info(f"Unpacking: {result}")
            # if someone is awaiting a response, fulfill the future
            if self._receive_future is not None and not self._receive_future.done():
                self._receive_future.set_result(payload)

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

    def send_and_receive(self, payload: Any, timeout: float = None) -> Any:
        """
        Send a payload and block until a response arrives on this pipe.

        Parameters
        ----------
        payload : Any
            The value to send through the pipe_output port.
        timeout : float, optional
            Maximum seconds to wait for a response. None means indefinite.

        Returns
        -------
        Any
            The first payload received by this pipe's input port.

        Raises
        ------
        concurrent.futures.TimeoutError
            If the response does not arrive within the given timeout.
        """
        loop = LoopRegistry.get_loop()
        # optionally clear history
        if getattr(self, 'store_received_payloads', False):
            self.clear_received_payloads()
        # prepare a future to capture the next incoming payload
        # ensure it is created on the shared loop
        self._receive_future = loop.create_future()
        # send payload into the flow
        self.send_payload(payload)
        # wrap the future in a coroutine so we can thread-safely wait on it
        async def _await_future():
            return await self._receive_future
        # schedule and block until the future is set or timeout expires
        concurrent = asyncio.run_coroutine_threadsafe(_await_future(), loop)
        try:
            return concurrent.result(timeout)
        finally:
            # clean up the internal future reference
            self._receive_future = None