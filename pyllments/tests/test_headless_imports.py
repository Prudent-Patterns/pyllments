"""Ensure core imports do not require Panel at import time."""
import sys

import pytest


def test_root_import_does_not_load_panel():
    # Fresh-ish check: panel may already be loaded by other tests in same session
    had_panel = "panel" in sys.modules
    import pyllments  # noqa: F401
    from pyllments import flow  # noqa: F401

    if not had_panel:
        assert "panel" not in sys.modules


def test_chat_interface_model_import_without_panel():
    had_panel = "panel" in sys.modules
    from pyllments.elements.chat_interface import ChatInterfaceModel  # noqa: F401

    if not had_panel:
        assert "panel" not in sys.modules


def test_message_payload_class_loads_without_panel():
    had_panel = "panel" in sys.modules
    from pyllments.payloads.message import MessagePayload  # noqa: F401

    if not had_panel:
        assert "panel" not in sys.modules


def test_component_view_works_when_panel_installed():
    pytest.importorskip("panel")

    from pyllments.payloads.message import MessagePayload

    p = MessagePayload(role="user", content="hi", mode="atomic")
    view = p.create_static_view(show_role=False)
    assert view is not None
