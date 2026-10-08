"""The chat-completions shape every backend sends."""

import json

import pytest

from pyllments.payloads import MessagePayload, ToolUsePayload
from pyllments.payloads.message.chat_completions import (
    message_to_chat_completion,
    to_chat_completions,
)


def _finished_tool_use(*, with_ids: bool = True) -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name="tools")
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="lookup",
        model_tool_name="functions_lookup",
        parameters={"name": "prednisone"},
        tool_call_id="call_1" if with_ids else None,
    )
    payload.model.attach_result(
        index,
        {"content": [{"type": "text", "text": "prednisone: found"}], "raw": None, "metadata": {}},
    )
    return payload


def test_assistant_tool_calls_are_sent_with_json_arguments():
    message = MessagePayload(
        role="assistant",
        content="",
        tool_calls=[{"id": "call_1", "type": "function",
                     "function": {"name": "functions_lookup", "arguments": {"name": "x"}}}],
    )
    entry = message_to_chat_completion(message)
    assert entry["content"] is None
    assert entry["tool_calls"][0]["id"] == "call_1"
    assert json.loads(entry["tool_calls"][0]["function"]["arguments"]) == {"name": "x"}


def test_tool_message_carries_its_call_id_and_name():
    message = MessagePayload(role="tool", content="ok", tool_call_id="call_1", tool_name="functions_lookup")
    entry = message_to_chat_completion(message)
    assert entry == {"role": "tool", "content": "ok", "tool_call_id": "call_1", "name": "functions_lookup"}


def test_tool_message_without_call_id_is_refused():
    with pytest.raises(ValueError, match="tool_call_id"):
        message_to_chat_completion(MessagePayload(role="tool", content="ok"))


def test_misspelled_message_field_is_an_error_not_a_silent_drop():
    with pytest.raises(TypeError, match="tool_call_idd"):
        MessagePayload(role="tool", content="ok", tool_call_idd="call_1")


def test_tool_use_payload_expands_in_place_after_its_assistant_message():
    assistant = MessagePayload(
        role="assistant",
        content="",
        tool_calls=[{"id": "call_1", "type": "function",
                     "function": {"name": "functions_lookup", "arguments": "{}"}}],
    )
    messages = to_chat_completions([
        MessagePayload(role="user", content="prednisone?"),
        assistant,
        _finished_tool_use(),
    ])
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[2]["tool_call_id"] == messages[1]["tool_calls"][0]["id"]
    assert messages[2]["content"] == "prednisone: found"


def test_tool_use_without_ids_falls_back_to_one_system_message():
    messages = to_chat_completions([_finished_tool_use(with_ids=False)])
    assert [m["role"] for m in messages] == ["system"]
    assert "prednisone: found" in messages[0]["content"]


def test_failed_and_denied_records_tell_the_model_why():
    payload = ToolUsePayload(executor_element_name="tools")
    failed = payload.model.add_tool_call(
        adapter_name="functions", tool_name="a", model_tool_name="functions_a", tool_call_id="c1"
    )
    denied = payload.model.add_tool_call(
        adapter_name="functions", tool_name="b", model_tool_name="functions_b",
        tool_call_id="c2", permission_required=True,
    )
    payload.model.attach_error(failed, {"type": "ToolExecutionError", "message": "boom", "retryable": True, "details": {}})
    payload.model.deny([denied], reason="not now")
    texts = [m["content"] for m in to_chat_completions([payload])]
    assert texts == ["Error: boom (retryable)", "Denied: not now"]


def test_unfinished_records_produce_no_messages():
    payload = ToolUsePayload(executor_element_name="tools")
    payload.model.add_proposed_call(model_tool_name="functions_lookup", tool_call_id="c1")
    assert payload.to_messages() == []
