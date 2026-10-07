"""The scripted mock plays tool rounds and records what it was shown."""

import json

import pytest

from pyllments.elements.llm_chat.mock_chat_model import MockChatModel
from pyllments.payloads import MessagePayload


def _user(text: str) -> MessagePayload:
    return MessagePayload(role="user", content=text)


@pytest.mark.asyncio
async def test_scripted_stream_reply_streams_text_then_tool_calls():
    model = MockChatModel(
        script=[{"content": "Looking that up.", "tool_calls": [
            {"name": "functions_lookup", "arguments": {"name": "prednisone"}}]}],
    )
    reply = model.generate_response([_user("prednisone?")])
    events = [event async for event in reply.model.aiter_events()]

    assert [e.type for e in events] == ["token", "token", "tool_call_delta", "tool_calls_complete", "done"]
    assert reply.model.content == "Looking that up."
    call = reply.model.tool_calls[0]
    assert call["id"] == "call_mock_1"
    assert json.loads(call["function"]["arguments"]) == {"name": "prednisone"}


def test_scripted_atomic_reply_and_echo_after_the_script():
    model = MockChatModel(output_mode="atomic", script=["First.", {"tool_calls": [{"name": "t", "arguments": {}}]}])
    first = model.generate_response([_user("a")])
    second = model.generate_response([_user("b")])
    third = model.generate_response([_user("c")])

    assert first.model.content == "First." and first.model.tool_calls == []
    assert second.model.tool_calls[0]["function"]["name"] == "t"
    assert third.model.content == "Mock: c"


def test_requests_record_the_messages_each_call_saw():
    model = MockChatModel(output_mode="atomic", script=["ok"])
    model.generate_response([
        MessagePayload(role="system", content="Be brief."),
        _user("hello"),
    ])
    assert model.requests == [[
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "hello"},
    ]]


def test_forced_write_card_still_plays_when_advertised():
    model = MockChatModel(
        output_mode="atomic",
        tools=[{"type": "function", "function": {"name": "write_card", "parameters": {}}}],
    )
    reply = model.generate_response([_user("we talked about sleep")])
    assert reply.model.tool_calls[0]["function"]["name"] == "write_card"
