from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload

def test_port_connection():
    """
    Connects the output port of one element to the input port of another
    and tests whether the connected elements in each port are indeed connected
    """
    el1 = Element()
    el2 = Element()

    el1.ports.add_output(name='some_output', payload_type=Payload)
    el2.ports.add_input(name='some_input', payload_type=Payload)

    el1.ports.output.some_output > el2.ports.input.some_input

    assert el1.ports.output.some_output.connected_elements[0] is el2
    assert el2.ports.input.some_input.connected_elements[0] is el1