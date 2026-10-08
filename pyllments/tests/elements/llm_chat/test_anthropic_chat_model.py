import json

import pytest

from pyllments.elements.llm_chat import AnthropicChatModel
from pyllments.payloads.message import MessagePayload


def _model(**kwargs) -> AnthropicChatModel:
    return AnthropicChatModel(api_key="sk-ant-test", **kwargs)


def _tool_turn() -> list[MessagePayload]:
    """System prompt, a user question, a reply that called two tools, both results, a notice."""
    calls = [
        {"id": "toolu_1", "type": "function", "function": {"name": "search", "arguments": '{"q": "a"}'}},
        {"id": "toolu_2", "type": "function", "function": {"name": "search", "arguments": '{"q": "b"}'}},
    ]
    return [
        MessagePayload(role="system", content="Be brief."),
        MessagePayload(role="system", content="Subject: Alex."),
        MessagePayload(role="user", content="Find a and b."),
        MessagePayload(role="assistant", content="", tool_calls=calls),
        MessagePayload(role="tool", content="a: found", tool_call_id="toolu_1", tool_name="search"),
        MessagePayload(role="tool", content="b: found", tool_call_id="toolu_2", tool_name="search"),
        MessagePayload(role="system", content="Round 2 of 4."),
    ]


def _recording_post(monkeypatch, events_per_call):
    calls = []

    async def fake_post(self, url, headers, body, *, stream):
        calls.append({"url": url, "headers": headers, "body": body, "stream": stream})
        events = events_per_call[len(calls) - 1]
        if not stream:
            return events

        async def gen():
            for event in events:
                yield event

        return gen()

    monkeypatch.setattr(AnthropicChatModel, "_http_post", fake_post)
    return calls


def _text_reply(text: str, usage: dict | None = None) -> list[dict]:
    return [
        {"type": "message_start", "message": {"usage": usage or {"input_tokens": 10, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}},
        {"type": "message_stop"},
    ]


def _thinking_tool_reply() -> list[dict]:
    return [
        {"type": "message_start", "message": {"usage": {
            "input_tokens": 40, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 60,
            "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-1"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "tool_use", "id": "toolu_9", "name": "search", "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"q": '}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '"pred"}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 25}},
        {"type": "message_stop"},
    ]


def test_request_puts_leading_system_in_system_and_keeps_the_notice_in_place():
    url, headers, body = _model()._request(_tool_turn(), stream=True)

    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body["system"] == [
        {"type": "text", "text": "Be brief."},
        {"type": "text", "text": "Subject: Alex.", "cache_control": {"type": "ephemeral"}},
    ]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "system"]
    assert body["messages"][-1] == {"role": "system", "content": "Round 2 of 4."}


def test_parallel_tool_results_share_one_user_turn_after_the_tool_use_blocks():
    _url, _headers, body = _model()._request(_tool_turn(), stream=True)
    assistant, results = body["messages"][1], body["messages"][2]

    assert assistant["content"] == [
        {"type": "tool_use", "id": "toolu_1", "name": "search", "input": {"q": "a"}},
        {"type": "tool_use", "id": "toolu_2", "name": "search", "input": {"q": "b"}},
    ]
    assert results["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "a: found"},
        {"type": "tool_result", "tool_use_id": "toolu_2", "content": "b: found"},
    ]


def test_request_caches_automatically_and_asks_anthropic_to_drop_stale_thinking():
    _url, headers, body = _model()._request(_tool_turn(), stream=True)

    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["thinking"] == {
        "type": "adaptive",
        "block_binding": {"prefix_mismatch_behavior": "drop_block"},
    }
    assert headers["anthropic-beta"] == "thinking-binding-controls-2026-08-01"
    assert body["max_tokens"] == 16000


def test_request_without_thinking_sends_no_thinking_and_no_beta():
    _url, headers, body = _model(thinking=None, cache="off")._request(_tool_turn(), stream=False)

    assert "thinking" not in body
    assert "anthropic-beta" not in headers
    assert "cache_control" not in body
    assert all("cache_control" not in block for block in body["system"])


def test_a_one_hour_cache_marks_both_breakpoints_alike():
    _url, _headers, body = _model(cache_ttl="1h")._request(_tool_turn(), stream=True)

    assert body["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_tools_and_tool_choice_are_translated():
    model = _model(
        tools=[{"type": "function", "function": {
            "name": "search", "description": "Find records.",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}}],
        model_args={"tool_choice": "none", "max_tokens": 2000, "output_config": {"effort": "low"}},
    )
    _url, _headers, body = model._request(_tool_turn(), stream=True)

    assert body["tools"] == [{
        "name": "search",
        "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "description": "Find records.",
    }]
    assert body["tool_choice"] == {"type": "none"}
    assert body["max_tokens"] == 2000
    assert body["output_config"] == {"effort": "low"}


@pytest.mark.asyncio
async def test_stream_yields_text_and_closes_with_usage(monkeypatch):
    _recording_post(monkeypatch, [_text_reply("Hello", usage={"input_tokens": 10, "output_tokens": 1})])
    reply = _model().generate_response([MessagePayload(role="user", content="Hi")])

    tokens = [token async for token in reply.model.aiter_tokens()]

    assert tokens == ["Hello"]
    assert reply.model.content == "Hello"
    assert reply.model.usage == {
        "input_tokens": 10, "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 3,
    }
    assert reply.model.reasoning is None


@pytest.mark.asyncio
async def test_stream_assembles_tool_calls_and_keeps_thinking_for_replay(monkeypatch):
    _recording_post(monkeypatch, [_thinking_tool_reply()])
    reply = _model().generate_response([MessagePayload(role="user", content="Find pred")])

    await reply.model.aget_message()

    assert reply.model.tool_calls == [{
        "id": "toolu_9", "type": "function",
        "function": {"name": "search", "arguments": '{"q": "pred"}'},
    }]
    assert reply.model.reasoning == {"provider": "anthropic", "content": [
        {"type": "thinking", "thinking": "", "signature": "sig-1"},
        {"type": "tool_use", "id": "toolu_9", "name": "search", "input": {"q": "pred"}},
    ]}
    # Anthropic's input_tokens leaves out the cached part; the record counts the whole prompt.
    assert reply.model.usage == {
        "input_tokens": 1000, "cached_input_tokens": 900, "cache_write_tokens": 60, "output_tokens": 25,
    }


def test_a_reply_with_anthropic_reasoning_goes_back_as_anthropic_returned_it():
    blocks = [
        {"type": "thinking", "thinking": "", "signature": "sig-1"},
        {"type": "tool_use", "id": "toolu_9", "name": "search", "input": {"q": "pred"}},
    ]
    reply = MessagePayload(
        role="assistant", content="",
        tool_calls=[{"id": "toolu_9", "type": "function",
                     "function": {"name": "search", "arguments": '{"q": "pred"}'}}],
        reasoning={"provider": "anthropic", "content": blocks},
    )
    turn = [
        MessagePayload(role="user", content="Find pred"),
        reply,
        MessagePayload(role="tool", content="pred: found", tool_call_id="toolu_9"),
    ]
    _url, _headers, body = _model()._request(turn, stream=True)

    assert body["messages"][1] == {"role": "assistant", "content": blocks}


def test_another_providers_record_is_ignored():
    reply = MessagePayload(
        role="assistant", content="Hi.",
        reasoning={"provider": "openai", "items": [{"type": "reasoning"}]},
    )
    _url, _headers, body = _model()._request(
        [MessagePayload(role="user", content="Hello"), reply], stream=True)

    assert body["messages"][1] == {"role": "assistant", "content": [{"type": "text", "text": "Hi."}]}


def test_a_system_message_after_a_reply_is_sent_as_user_text():
    history = [
        MessagePayload(role="user", content="Hello"),
        MessagePayload(role="assistant", content="Hi."),
        MessagePayload(role="system", content="Summary so far."),
        MessagePayload(role="user", content="Next"),
    ]
    _url, _headers, body = _model()._request(history, stream=True)

    assert body["messages"][2] == {"role": "user", "content": [
        {"type": "text", "text": "Summary so far."},
        {"type": "text", "text": "Next"},
    ]}


@pytest.mark.asyncio
async def test_a_refusal_ends_the_stream_with_an_error(monkeypatch):
    events = _text_reply("I can't")
    events[-2] = {"type": "message_delta",
                  "delta": {"stop_reason": "refusal", "stop_details": {"category": "bio"}}}
    _recording_post(monkeypatch, [events])
    reply = _model().generate_response([MessagePayload(role="user", content="Hi")])

    with pytest.raises(ValueError, match="refusal, category bio"):
        await reply.model.aget_message()


@pytest.mark.asyncio
async def test_atomic_reply_reads_blocks_usage_and_record(monkeypatch):
    response = {
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig-2"},
            {"type": "text", "text": "Looking."},
            {"type": "tool_use", "id": "toolu_3", "name": "search", "input": {"q": "x"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "cache_read_input_tokens": 95, "output_tokens": 7},
    }
    calls = _recording_post(monkeypatch, [response])
    reply = _model(output_mode="atomic").generate_response([MessagePayload(role="user", content="x?")])

    content = await reply.model.aget_message()

    assert calls[0]["stream"] is False
    assert content == "Looking."
    assert json.loads(reply.model.tool_calls[0]["function"]["arguments"]) == {"q": "x"}
    assert reply.model.usage["input_tokens"] == 100
    assert reply.model.reasoning["content"] == response["content"]


@pytest.mark.asyncio
async def test_dropped_thinking_is_reported_not_silent(monkeypatch):
    from loguru import logger

    events = _text_reply("Hi")
    events[0] = {"type": "message_start", "message": {
        "usage": {"input_tokens": 10, "output_tokens": 1},
        "input_transformations": [
            {"type": "thinking_dropped", "path": "messages.2.content.0", "reason": "prefix_binding_mismatch"},
        ],
    }}
    _recording_post(monkeypatch, [events])
    warnings = []
    # Pyllments keeps its logs off until the application turns them on.
    logger.enable("pyllments")
    sink = logger.add(lambda message: warnings.append(str(message)), level="WARNING")
    try:
        reply = _model().generate_response([MessagePayload(role="user", content="Hi")])
        await reply.model.aget_message()
    finally:
        logger.remove(sink)
        logger.disable("pyllments")

    assert any("dropped 1 sent-back thinking block" in line and "messages.2.content.0" in line
               for line in warnings)


def test_a_model_that_rejects_forced_tool_calls_gets_auto():
    forced = {"type": "function", "function": {"name": "write_card"}}
    sonnet = _model(model_name="claude-sonnet-5-5", model_args={"tool_choice": forced})
    haiku = _model(model_name="claude-haiku-5-5", model_args={"tool_choice": forced})

    assert sonnet._request(_tool_turn(), stream=False)[2]["tool_choice"] == {"type": "auto"}
    assert haiku._request(_tool_turn(), stream=False)[2]["tool_choice"] == {"type": "tool", "name": "write_card"}


def test_models_before_adaptive_thinking_get_no_thinking_field():
    _url, headers, body = _model(model_name="claude-haiku-4-5")._request(_tool_turn(), stream=True)

    assert "thinking" not in body
    assert "anthropic-beta" not in headers
