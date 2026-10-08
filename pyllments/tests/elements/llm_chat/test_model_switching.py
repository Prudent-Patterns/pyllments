"""One ``provider/model`` string picks the backend; each request reports whether it only appended."""

import pytest

from pyllments.elements import LLMChatElement
from pyllments.elements.llm_chat.model_routing import route_model
from pyllments.payloads import MessagePayload


def test_a_provider_prefix_picks_the_backend():
    assert route_model("anthropic/claude-haiku-5-5") == ("anthropic", "claude-haiku-5-5")
    assert route_model("openai/gpt-5.5") == ("openai", "gpt-5.5")
    assert route_model("@cf/meta/llama-3.3-70b-instruct-fp8-fast") == (
        "cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    assert route_model("cloudflare/openai/gpt-5.5") == ("cloudflare", "openai/gpt-5.5")
    with pytest.raises(ValueError, match="anthropic/"):
        route_model("claude-haiku-5-5")


def test_auto_builds_the_routed_backend_with_its_own_settings():
    llm = LLMChatElement(
        backend="auto",
        model_name="anthropic/claude-haiku-5-5",
        provider_params={"anthropic": {"api_key": "sk-ant"}, "openai": {"api_key": "sk-oai"}},
    )
    assert type(llm.model).__name__ == "AnthropicChatModel"
    assert (llm.model.model_name, llm.model.api_key) == ("claude-haiku-5-5", "sk-ant")

    llm.model.tools = [{"type": "function", "function": {"name": "search"}}]
    llm.set_model("openai/gpt-5.5")

    assert type(llm.model).__name__ == "OpenAIChatModel"
    assert (llm.model.model_name, llm.model.api_key) == ("gpt-5.5", "sk-oai")
    assert llm.model.tools[0]["function"]["name"] == "search"


def test_set_model_needs_auto():
    llm = LLMChatElement(backend="mock")
    with pytest.raises(ValueError, match="auto"):
        llm.set_model("anthropic/claude-haiku-5-5")


def _user(text):
    return MessagePayload(role="user", content=text)


def test_each_request_reports_whether_it_only_appended():
    llm = LLMChatElement(backend="mock", output_mode="atomic", script=["a", "b", "c", "d"])
    system = MessagePayload(role="system", content="Be brief.")
    first_user = _user("one")
    reply = MessagePayload(role="assistant", content="a")

    first = llm._generate_with_options([system, first_user])
    appended = llm._generate_with_options([system, first_user, reply, _user("two")])
    edited = llm._generate_with_options([system, _user("ONE"), reply, _user("two")])

    assert first.model.request_check["first_request"] is True
    assert appended.model.request_check == {
        "first_request": False, "appended": True, "changed_at": None,
        "same_turn": False, "settings_changed": False,
    }
    assert edited.model.request_check["appended"] is False
    assert edited.model.request_check["changed_at"] == 1
    assert edited.model.request_check["same_turn"] is True


def test_one_shot_options_count_as_a_settings_change():
    llm = LLMChatElement(backend="mock", output_mode="atomic", script=["a", "b"])
    llm._generate_with_options([_user("one")])
    llm._next_request_options = {"tool_choice": "none"}
    response = llm._generate_with_options([_user("one"), MessagePayload(role="assistant", content="a")])

    assert response.model.request_check["appended"] is True
    assert response.model.request_check["settings_changed"] is True
