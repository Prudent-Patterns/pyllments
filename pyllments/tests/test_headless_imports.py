"""Ensure light-edition imports do not load Panel or host LLM SDKs."""
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = str(Path(__file__).resolve().parents[2])

_WORKER_CHAT_IMPORTS = """
import sys

from pyllments.elements.chat_gateway import ChatGatewayElement
from pyllments.elements.context_builder import ContextBuilderElement
from pyllments.elements.history_handler import HistoryHandlerElement
from pyllments.elements.llm_chat import LLMChatElement
from pyllments.payloads.message import MessagePayload

forbidden = {"panel", "litellm", "openrouter"}
loaded = forbidden & set(sys.modules)
assert not loaded, loaded
assert ChatGatewayElement is not None
assert ContextBuilderElement is not None
assert HistoryHandlerElement is not None
assert LLMChatElement is not None
assert MessagePayload is not None
"""

_ELEMENT_IMPORT_SKIPS_DOTENV = """
import sys

from pyllments.base.element_base import Element

assert "dotenv" not in sys.modules
assert Element is not None
"""


def _run_fresh(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_root_import_does_not_load_panel():
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


_CLOUDFLARE_BACKEND_SKIPS_HOST_SDKS = """
import sys

from pyllments.elements.llm_chat import LLMChatElement

element = LLMChatElement(backend="cloudflare", account_id="acct", api_key="token")
forbidden = {"panel", "litellm", "openrouter"}
loaded = forbidden & set(sys.modules)
assert not loaded, loaded
assert element.model.__class__.__name__ == "CloudflareAIGatewayChatModel"
"""


def test_worker_chat_imports_stay_headless():
    _run_fresh(_WORKER_CHAT_IMPORTS)


def test_cloudflare_backend_does_not_load_host_llm_sdks():
    _run_fresh(_CLOUDFLARE_BACKEND_SKIPS_HOST_SDKS)


def test_element_import_does_not_load_dotenv():
    _run_fresh(_ELEMENT_IMPORT_SKIPS_DOTENV)


def test_component_view_works_when_panel_installed():
    pytest.importorskip("panel")

    from pyllments.payloads.message import MessagePayload

    p = MessagePayload(role="user", content="hi", mode="atomic")
    view = p.create_static_view(show_role=False)
    assert view is not None
