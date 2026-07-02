"""Regression tests for component/port object identity cleanup."""

import pytest

from pyllments.base.component_base import Component
from pyllments.base.element_base import Element
from pyllments.base.payload_base import Payload


def test_component_id_not_in_param():
    assert "id" not in Component.param


def test_component_id_deprecation_on_access():
    element = Element()
    with pytest.warns(DeprecationWarning, match="Component.id is deprecated"):
        _ = element.id


def test_component_id_deprecation_on_constructor():
    with pytest.warns(DeprecationWarning, match="Passing id= to Component is deprecated"):
        element = Element(id="legacy-123")
    with pytest.warns(DeprecationWarning, match="Component.id is deprecated"):
        assert element.id == "legacy-123"


def test_component_id_deprecation_on_setter():
    element = Element()
    with pytest.warns(DeprecationWarning, match="Component.id is deprecated"):
        element.id = "custom"
    with pytest.warns(DeprecationWarning, match="Component.id is deprecated"):
        assert element.id == "custom"


def test_components_with_same_name_are_distinct():
    first = Element(name="shared")
    second = Element(name="shared")
    assert first is not second
    assert first != second  # object identity, not name-based equality


def test_port_id_not_in_param():
    from pyllments.ports.ports import Port

    assert "id" not in Port.param


def test_port_has_no_id_attribute():
    element = Element()

    def unpack(payload: int):
        pass

    port = element.ports.add_input(
        name="in",
        unpack_payload_callback=unpack,
        payload_type=int,
    )
    with pytest.raises(AttributeError):
        _ = port.id


def test_payload_view_cache_not_in_param():
    assert "view_cache" not in Payload.param


@pytest.mark.asyncio
async def test_port_validation_cache_reuses_same_output_port():
    """Second emit through the same output port should not re-validate."""
    sender = Element(name="sender")
    receiver = Element(name="receiver")
    seen = []

    async def pack(payload: int) -> int:
        return payload

    def unpack(payload: int):
        seen.append(payload)

    out = sender.ports.add_output(name="out", pack_payload_callback=pack)
    inn = receiver.ports.add_input(
        name="in",
        unpack_payload_callback=unpack,
        payload_type=int,
    )
    out > inn

    await out.stage_emit(payload=1)
    await out.stage_emit(payload=2)

    assert seen == [1, 2]
    assert any(port is out for port in inn._validated_output_ports)
    await out.close()
