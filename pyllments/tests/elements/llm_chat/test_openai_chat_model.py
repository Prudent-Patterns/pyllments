import pytest

from pyllments.elements.llm_chat import OpenAIChatModel
from pyllments.payloads.message import MessagePayload


def _model(**kwargs) -> OpenAIChatModel:
    return OpenAIChatModel(api_key="sk-test", **kwargs)


def _tool_turn() -> list[MessagePayload]:
    calls = [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"q": "a"}'}}]
    return [
        MessagePayload(role="system", content="Be brief."),
        MessagePayload(role="user", content="Find a."),
        MessagePayload(role="assistant", content="", tool_calls=calls),
        MessagePayload(role="tool", content="a: found", tool_call_id="call_1", tool_name="search"),
        MessagePayload(role="system", content="Round 2 of 4."),
    ]


def _recording_post(monkeypatch, responses):
    calls = []

    async def fake_post(self, url, headers, body, *, stream):
        calls.append({"url": url, "headers": headers, "body": body, "stream": stream})
        response = responses[len(calls) - 1]
        if not stream:
            return response

        async def gen():
            for event in response:
                yield event

        return gen()

    monkeypatch.setattr(OpenAIChatModel, "_http_post", fake_post)
    return calls


def test_request_is_stateless_and_keeps_every_message_in_place():
    url, headers, body = _model()._request(_tool_turn(), stream=True)

    assert url == "https://api.openai.com/v1/responses"
    assert headers["Authorization"] == "Bearer sk-test"
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["input"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Find a."},
        {"type": "function_call", "call_id": "call_1", "name": "search", "arguments": '{"q": "a"}'},
        {"type": "function_call_output", "call_id": "call_1", "output": "a: found"},
        {"role": "system", "content": "Round 2 of 4."},
    ]


def test_tools_tool_choice_and_limits_are_translated():
    model = _model(
        tools=[{"type": "function", "function": {
            "name": "search", "description": "Find records.",
            "parameters": {"type": "object", "properties": {}}}}],
        model_args={"tool_choice": "none", "max_tokens": 500, "reasoning": {"effort": "low"}},
        response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": {"type": "object"}}},
        prompt_cache_key="person-1",
    )
    _url, _headers, body = model._request(_tool_turn(), stream=False)

    assert body["tools"] == [{
        "type": "function", "name": "search",
        "parameters": {"type": "object", "properties": {}}, "description": "Find records.",
    }]
    assert body["tool_choice"] == "none"
    assert body["max_output_tokens"] == 500
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"] == {"format": {"type": "json_schema", "name": "answer", "schema": {"type": "object"}}}
    assert body["prompt_cache_key"] == "person-1"


def _reasoning_tool_reply() -> list[dict]:
    output = [
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc-1"},
        {"type": "function_call", "id": "fc_1", "call_id": "call_9", "name": "search", "arguments": '{"q": "pred"}'},
    ]
    return [
        {"type": "response.created", "response": {}},
        {"type": "response.output_item.added", "output_index": 0, "item": output[0]},
        {"type": "response.output_item.added", "output_index": 1,
         "item": {"type": "function_call", "id": "fc_1", "call_id": "call_9", "name": "search", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"q": '},
        {"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '"pred"}'},
        {"type": "response.completed", "response": {
            "output": output,
            "usage": {"input_tokens": 1000, "input_tokens_details": {"cached_tokens": 900},
                      "output_tokens": 30}}},
    ]


@pytest.mark.asyncio
async def test_stream_assembles_tool_calls_and_keeps_reasoning_for_replay(monkeypatch):
    _recording_post(monkeypatch, [_reasoning_tool_reply()])
    reply = _model().generate_response([MessagePayload(role="user", content="Find pred")])

    await reply.model.aget_message()

    assert reply.model.tool_calls == [{
        "id": "call_9", "type": "function",
        "function": {"name": "search", "arguments": '{"q": "pred"}'},
    }]
    assert reply.model.reasoning["provider"] == "openai"
    assert [item["type"] for item in reply.model.reasoning["items"]] == ["reasoning", "function_call"]
    assert reply.model.usage == {
        "input_tokens": 1000, "cached_input_tokens": 900, "cache_write_tokens": 0, "output_tokens": 30,
    }


@pytest.mark.asyncio
async def test_stream_yields_text(monkeypatch):
    events = [
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed", "response": {"output": [], "usage": {"input_tokens": 5, "output_tokens": 2}}},
    ]
    _recording_post(monkeypatch, [events])
    reply = _model().generate_response([MessagePayload(role="user", content="Hi")])

    tokens = [token async for token in reply.model.aiter_tokens()]

    assert tokens == ["Hel", "lo"]
    assert reply.model.reasoning is None
    assert reply.model.usage["output_tokens"] == 2


def test_a_reply_with_openai_reasoning_goes_back_as_openai_returned_it():
    items = [
        {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc-1"},
        {"type": "function_call", "id": "fc_1", "call_id": "call_9", "name": "search", "arguments": "{}"},
    ]
    reply = MessagePayload(
        role="assistant", content="",
        tool_calls=[{"id": "call_9", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
        reasoning={"provider": "openai", "items": items},
    )
    turn = [
        MessagePayload(role="user", content="Find"),
        reply,
        MessagePayload(role="tool", content="found", tool_call_id="call_9"),
    ]
    _url, _headers, body = _model()._request(turn, stream=True)

    assert body["input"][1:3] == items
    assert body["input"][3] == {"type": "function_call_output", "call_id": "call_9", "output": "found"}


@pytest.mark.asyncio
async def test_a_failed_response_ends_the_stream_with_an_error(monkeypatch):
    events = [{"type": "response.failed", "response": {"error": {"code": "server_error"}}}]
    _recording_post(monkeypatch, [events])
    reply = _model().generate_response([MessagePayload(role="user", content="Hi")])

    with pytest.raises(ValueError, match="server_error"):
        await reply.model.aget_message()


@pytest.mark.asyncio
async def test_atomic_reply_reads_output_items(monkeypatch):
    response = {
        "status": "completed",
        "output": [
            {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "Hello."}]},
        ],
        "usage": {"input_tokens": 12, "output_tokens": 2},
    }
    calls = _recording_post(monkeypatch, [response])
    reply = _model(output_mode="atomic").generate_response([MessagePayload(role="user", content="Hi")])

    assert await reply.model.aget_message() == "Hello."
    assert calls[0]["stream"] is False
    assert reply.model.usage["input_tokens"] == 12
