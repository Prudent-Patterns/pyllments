"""Workers AI native results keep their tool calls when normalized."""

import json

from pyllments.elements.llm_chat.cloudflare_ai_gateway_chat_model import (
    _completion_from_binding,
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


def test_messages_take_workers_ai_shape_for_the_binding():
    native = _native_messages([
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "prednisone?"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{\"query\": \"prednisone\"}"}}]},
        {"role": "tool", "content": "{\"items\": []}", "tool_call_id": "call_1", "name": "search"},
    ])
    assert native[2] == {"role": "assistant", "content": "", "tool_calls": [{"name": "search", "arguments": {"query": "prednisone"}}]}
    assert native[3] == {"role": "tool", "content": "{\"items\": []}", "name": "search"}
    assert all(isinstance(m["content"], str) for m in native)
    assert "tool_call_id" not in native[3]

