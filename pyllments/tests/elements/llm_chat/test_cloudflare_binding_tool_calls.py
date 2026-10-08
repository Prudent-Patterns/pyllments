"""Workers AI native results keep their tool calls when normalized."""

import json

import pytest

from pyllments.elements.llm_chat.cloudflare_ai_gateway_chat_model import (
    CloudflareAIGatewayChatModel,
    _completion_from_binding,
    _is_transient,
    _native_messages,
)


def test_native_tool_calls_get_ids_and_json_arguments():
    completion = _completion_from_binding({
        "response": "",
        "tool_calls": [{"name": "functions_lookup", "arguments": {"name": "prednisone"}}],
    })
    message = completion["choices"][0]["message"]
    call = message["tool_calls"][0]
    assert call["id"] == "call_0"
    assert call["function"]["name"] == "functions_lookup"
    assert json.loads(call["function"]["arguments"]) == {"name": "prednisone"}
    assert completion["choices"][0]["finish_reason"] == "tool_calls"


def test_plain_text_result_still_normalizes():
    completion = _completion_from_binding({"response": "hello"})
    assert completion["choices"][0]["message"]["content"] == "hello"
    assert completion["choices"][0]["message"]["tool_calls"] == []


def test_binding_messages_keep_openai_shape_but_never_null_content():
    native = _native_messages([
        {"role": "user", "content": "prednisone?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{\"query\": \"prednisone\"}"}}]},
        {"role": "tool", "content": "{\"items\": []}", "tool_call_id": "call_1", "name": "search"},
    ])
    assert native[1]["content"] == ""
    assert native[1]["tool_calls"][0] == {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{\"query\": \"prednisone\"}"}}
    assert native[2] == {"role": "tool", "content": "{\"items\": []}", "tool_call_id": "call_1", "name": "search"}


class _FlakyBinding:
    def __init__(self, failures: list[Exception]):
        self.failures = failures
        self.calls = 0

    async def run(self, model, inputs, options):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return {"response": "ok", "tool_calls": []}


@pytest.mark.asyncio
async def test_a_busy_provider_is_retried_before_the_model_sees_anything():
    binding = _FlakyBinding([RuntimeError("AiError: 503 service overloaded")])
    model = CloudflareAIGatewayChatModel(ai_binding=binding, retry_backoff=0)
    completion = await model._binding_completion({"messages": [{"role": "user", "content": "hi"}]})
    assert binding.calls == 2
    assert completion["choices"][0]["message"]["content"] == "ok"


@pytest.mark.asyncio
async def test_a_bad_request_is_not_retried():
    binding = _FlakyBinding([RuntimeError("AiError: 8007: 400 Bad Request validation errors")])
    model = CloudflareAIGatewayChatModel(ai_binding=binding, retry_backoff=0)
    with pytest.raises(RuntimeError, match="400"):
        await model._binding_completion({"messages": []})
    assert binding.calls == 1


def test_transient_classifier():
    assert _is_transient(RuntimeError("429 Too Many Requests"))
    assert _is_transient(RuntimeError("request timed out"))
    assert not _is_transient(RuntimeError("401 unauthorized"))
    assert not _is_transient(RuntimeError("something else"))


def test_a_call_written_as_text_becomes_a_call_and_no_words():
    completion = _completion_from_binding({
        "response": '{"name": "search", "parameters": {"query": "walking", "types": "[\\"plan\\"]"}}',
    })
    message = completion["choices"][0]["message"]
    assert message["content"] == ""
    assert message["tool_calls"][0]["function"]["name"] == "search"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"])["query"] == "walking"


def test_ordinary_json_in_a_reply_is_left_alone():
    completion = _completion_from_binding({"response": '{"answer": "yes", "count": 2}'})
    assert completion["choices"][0]["message"]["tool_calls"] == []
    assert completion["choices"][0]["message"]["content"].startswith("{")

