"""
Two rounds of one turn, through the real graph on the scripted mock, no gateway.

Proves the payloads, the ledger and the context builder carry a tool round in
native form. The turn machinery that drives the loop is the gateway's own test.
"""

import json

import pytest

from pyllments.elements import (
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
    PipeElement,
    ToolUseElement,
)
from pyllments.payloads import MessagePayload


def lookup(name: str) -> str:
    """Find a record by name."""
    return f"{name}: found"


@pytest.mark.asyncio
async def test_second_request_pairs_the_call_with_its_result():
    tools = ToolUseElement(name="tools", functions=[lookup])
    llm = LLMChatElement(
        backend="mock",
        output_mode="atomic",
        script=[
            {"content": "", "tool_calls": [
                {"name": "functions_lookup", "arguments": {"name": "prednisone"}}]},
            "Prednisone is on your list.",
        ],
    )
    history = HistoryHandlerElement(
        context_token_limit=8000,
        summary_token_threshold=0,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    user = PipeElement(name="user")
    results = PipeElement(name="results")
    bound = PipeElement(name="bound")

    user.ports.pipe_output > history.ports.payload_pre_emit_input
    results.ports.pipe_output > history.ports.payload_emit_input
    llm.ports.message_output > history.ports.payload_input
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

    # Round 1: the model asks for a tool. Its calls go out after the reply's delivery.
    await user.async_send_payload(MessagePayload(role="user", content="Is prednisone on my list?"))
    await llm.ports.output["tool_use_output"].drain()
    assert len(bound.received_payloads) == 1
    tool_use = bound.received_payloads[0]
    assert tool_use.model.status == "approved"

    # The executor runs the call; the finished payload is a new arrival and fires round 2.
    await tool_use.execute_approved()
    await results.async_send_payload(tool_use)
    await llm.ports.output["tool_use_output"].drain()

    requests = llm.model.requests
    assert len(requests) == 2
    second = requests[1]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assistant, tool = second[2], second[3]
    assert assistant["tool_calls"][0]["id"] == tool["tool_call_id"]
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"name": "prednisone"}
    assert tool["content"] == "prednisone: found"
    assert tool["name"] == "functions_lookup"
