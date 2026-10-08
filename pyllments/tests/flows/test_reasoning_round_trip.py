"""
Two rounds of one turn on the Anthropic backend, through the real ledger and builder.

Proves a reply's thinking survives the ledger and the context builder and
reaches the next round's request exactly as Anthropic returned it. The
provider is a recorded stream; no network.
"""

import pytest

from pyllments.elements import (
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
    PipeElement,
    ToolUseElement,
)
from pyllments.elements.llm_chat import AnthropicChatModel
from pyllments.payloads import MessagePayload


def lookup(name: str) -> str:
    """Find a record by name."""
    return f"{name}: found"


ROUND_ONE = [
    {"type": "message_start", "message": {"usage": {"input_tokens": 30, "output_tokens": 1}}},
    {"type": "content_block_start", "index": 0,
     "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-r1"}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1,
     "content_block": {"type": "tool_use", "id": "toolu_1", "name": "functions_lookup", "input": {}}},
    {"type": "content_block_delta", "index": 1,
     "delta": {"type": "input_json_delta", "partial_json": '{"name": "prednisone"}'}},
    {"type": "content_block_stop", "index": 1},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}},
    {"type": "message_stop"},
]

ROUND_TWO = [
    {"type": "message_start", "message": {"usage": {"input_tokens": 12, "cache_read_input_tokens": 40,
                                                    "output_tokens": 1}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0,
     "delta": {"type": "text_delta", "text": "Prednisone is on your list."}},
    {"type": "content_block_stop", "index": 0},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 8}},
    {"type": "message_stop"},
]


@pytest.mark.asyncio
async def test_the_second_request_sends_round_one_back_as_anthropic_returned_it(monkeypatch):
    bodies = []

    async def fake_post(self, url, headers, body, *, stream):
        bodies.append(body)
        events = [ROUND_ONE, ROUND_TWO][len(bodies) - 1]

        async def gen():
            for event in events:
                yield event

        return gen()

    monkeypatch.setattr(AnthropicChatModel, "_http_post", fake_post)

    tools = ToolUseElement(name="tools", functions=[lookup])
    llm = LLMChatElement(backend="anthropic", api_key="sk-ant-test", generate_content_on_emit=True)
    history = HistoryHandlerElement(
        context_token_limit=8000,
        summary_token_threshold=0,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    user = PipeElement(name="user")
    results = PipeElement(name="results")
    bound = PipeElement(name="bound")
    replies = PipeElement(name="replies")

    user.ports.pipe_output > history.ports.payload_pre_emit_input
    results.ports.pipe_output > history.ports.payload_emit_input
    llm.ports.message_output > history.ports.payload_input
    llm.ports.message_output > replies.ports.pipe_input
    ContextBuilderElement(
        input_map={
            "system_constant": {"role": "system", "message": "Be brief."},
            "history": {"ports": [history.ports.context_output]},
            "user_query": {"ports": [user.ports.pipe_output]},
            "tool_results": {"ports": [results.ports.pipe_output]},
        },
        trigger_map={
            "user_query": ["system_constant", "[history]", "user_query"],
            "tool_results": ["system_constant", "history"],
        },
        outgoing_input_ports=[llm.ports.messages_emit_input],
    )
    tools.ports.tools_output > llm.ports.tools_input
    llm.ports.tool_use_output > tools.ports.tool_use_input
    tools.ports.tool_use_output > bound.ports.pipe_input

    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    await user.async_send_payload(MessagePayload(role="user", content="Is prednisone on my list?"))
    await llm.ports.output["tool_use_output"].drain()
    tool_use = bound.received_payloads[0]
    await tool_use.execute_approved()
    await results.async_send_payload(tool_use)
    await llm.ports.output["tool_use_output"].drain()

    assert len(bodies) == 2
    second = bodies[1]
    assert second["system"] == [
        {"type": "text", "text": "Be brief.", "cache_control": {"type": "ephemeral"}},
    ]
    assert [m["role"] for m in second["messages"]] == ["user", "assistant", "user"]
    assert second["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "", "signature": "sig-r1"},
        {"type": "tool_use", "id": "toolu_1", "name": "functions_lookup", "input": {"name": "prednisone"}},
    ]
    assert second["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "prednisone: found"},
    ]

    first_reply, second_reply = replies.received_payloads
    assert first_reply.model.usage["output_tokens"] == 20
    assert second_reply.model.content == "Prednisone is on your list."
    assert second_reply.model.usage == {
        "input_tokens": 52, "cached_input_tokens": 40, "cache_write_tokens": 0, "output_tokens": 8,
    }


@pytest.mark.asyncio
async def test_through_the_gateway_each_request_only_appends(monkeypatch):
    """The notice stays where Claude saw it, so its thinking stays valid in round 2."""
    from pyllments.elements import ChatGatewayElement

    round_one = [dict(event) for event in ROUND_ONE]
    round_one[4] = {"type": "content_block_start", "index": 1,
                    "content_block": {"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {}}}
    bodies = []

    async def fake_post(self, url, headers, body, *, stream):
        bodies.append(body)
        events = [round_one, ROUND_TWO][len(bodies) - 1]

        async def gen():
            for event in events:
                yield event

        return gen()

    monkeypatch.setattr(AnthropicChatModel, "_http_post", fake_post)

    tools = ToolUseElement(name="tools", functions=[lookup], prefix_names=False)
    llm = LLMChatElement(backend="anthropic", api_key="sk-ant-test")
    history = HistoryHandlerElement(
        context_token_limit=8000, summary_token_threshold=0,
        projection_tiers={0: {}}, tokenizer_model="gpt-4o",
    )
    gateway = ChatGatewayElement(turn_notice_template="Round {{ round }}.")
    gateway.ports.request_options_output > llm.ports.request_options_input
    gateway.ports.message_output > history.ports.payload_emit_input
    gateway.ports.tool_result_output > history.ports.payload_emit_input
    llm.ports.message_output > gateway.ports.assistant_message_input
    gateway.ports.assistant_message_output > history.ports.payload_input
    gateway.ports.turn_notice_output > history.ports.payload_input
    ContextBuilderElement(
        input_map={
            "system_constant": {"role": "system", "message": "Be brief."},
            "history": {"ports": [history.ports.context_output]},
            "turn_notice": {"ports": [gateway.ports.turn_notice_output]},
        },
        trigger_map={"turn_notice": ["system_constant", "history", "turn_notice"]},
        outgoing_input_ports=[llm.ports.messages_emit_input],
    )
    tools.ports.tools_output > llm.ports.tools_input
    llm.ports.tool_use_output > tools.ports.tool_use_input
    tools.ports.tool_use_output > gateway.ports.tool_use_input
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("Is prednisone on my list?")
    events = [event async for event in turn.stream()]

    assert events[-1].type == "done"
    first, second = bodies
    assert first["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Is prednisone on my list?"}]},
        {"role": "system", "content": "Round 1."},
    ]
    assert second["messages"][: len(first["messages"])] == first["messages"]
    assert second["messages"][2]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-r1"}
    assert second["messages"][3]["content"][0]["type"] == "tool_result"
    assert second["messages"][4] == {"role": "system", "content": "Round 2."}
    assert second["system"][-1]["cache_control"] == {"type": "ephemeral"}
