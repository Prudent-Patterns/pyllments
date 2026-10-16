"""Templates compile once per source; renders reuse them."""

import jinja2
import pytest

from pyllments.common.jinja_cache import strict_template
from pyllments.elements.chat_gateway.chat_gateway_model import ChatGatewayModel
from pyllments.payloads.tool_use import ToolUsePayload


def test_the_same_source_compiles_once():
    assert strict_template("Hello {{ name }}") is strict_template("Hello {{ name }}")


def test_a_missing_variable_still_fails():
    with pytest.raises(jinja2.exceptions.UndefinedError):
        strict_template("Hello {{ name }}").render()


def test_the_turn_notice_renders_without_recompiling():
    gateway = ChatGatewayModel(turn_notice_template="Answer in words now.")
    gateway.render_turn_notice("turn-1")
    compiled = strict_template.cache_info().misses

    assert gateway.render_turn_notice("turn-2") == "Answer in words now."
    assert strict_template.cache_info().misses == compiled


def test_tool_use_payloads_share_one_results_template():
    first, second = ToolUsePayload(tool_calls=[]), ToolUsePayload(tool_calls=[])
    assert first.model.template is second.model.template
