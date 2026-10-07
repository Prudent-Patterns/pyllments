"""Workers AI native results keep their tool calls when normalized."""

import json

from pyllments.elements.llm_chat.cloudflare_ai_gateway_chat_model import _completion_from_binding


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
