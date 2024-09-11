from typing import Any

import param

from pyllments.base.element_base import Element


class TestElement(Element):
    """
    Element used to test the inputs and outputs of other elements.
    When set up as an input element, it will store the received payloads in a list.
    When set up as an output element, it will emit the the specified payload with send_payload
    """
    received_payloads = param.List(default=[], doc="List of received payloads")

    def __init__(self, **params):
        super().__init__(**params)
        self._setup_ports()

    def _setup_ports(self):
        def unpack(payload: Any):
            """Store the received payload"""
            self.received_payloads.append(payload)
            
        self.ports.add_input(
            name='test_input',
            unpack_payload_callback=unpack
        )

        def pack(payload: Any) -> Any:
            """Return the stored output payload"""
            return payload
        # Setup output port
        self.ports.add_output(
            name='test_output',
            pack_payload_callback=pack
        )

    def clear_received_payloads(self):
        """Clear the list of received payloads"""
        self.received_payloads = []

    def send_payload(self, payload: Any):
        self.ports.output['test_output'].stage_emit(payload=payload)
