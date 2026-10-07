"""
A turn with tool rounds, driven by the gateway through the whole graph.

One door per source into the history handler: the user message through
``payload_pre_emit_input`` (projection out, then ingest), tool results through
``payload_emit_input`` (ingest, then projection out), the assistant reply
through ``payload_input`` (ingest only). The builder has two triggers: the
user message for the first round, the tool results for every later one.
"""

import json

import pytest

from pyllments.elements import (
    ChatGatewayElement,
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
    ToolUseElement,
)


def lookup(name: str) -> str:
    """Find a record by name."""
    return f"{name}: found"


def _lookup_call(name: str = "prednisone") -> dict:
    return {"content": "", "tool_calls": [{"name": "lookup", "arguments": {"name": name}}]}


def _graph(script, *, output_mode: str, max_tool_rounds: int = 6):
    tools = ToolUseElement(name="tools", functions=[lookup], prefix_names=False)
    llm = LLMChatElement(backend="mock", output_mode=output_mode, script=script)
    history = HistoryHandlerElement(
        context_token_limit=8000, summary_token_threshold=0,
        projection_tiers={0: {}}, tokenizer_model="gpt-4o",
    )
    gateway = ChatGatewayElement(max_tool_rounds=max_tool_rounds)

    # The ledger takes each arrival before the builder sees it: connect these first.
    gateway.ports.message_output > history.ports.payload_pre_emit_input
    gateway.ports.tool_result_output > history.ports.payload_emit_input
    llm.ports.message_output > gateway.ports.assistant_message_input
    gateway.ports.assistant_message_output > history.ports.payload_input

    ContextBuilderElement(
        input_map={
            "system_constant": {"role": "system", "message": "Be brief."},
            "history": {"ports": [history.ports.context_output]},
            "user_query": {"ports": [gateway.ports.message_output]},
            "tool_results": {"ports": [gateway.ports.tool_result_output]},
        },
        trigger_map={
            "user_query": ["system_constant", "[history]", "user_query"],
            "tool_results": ["system_constant", "history"],
        },
        outgoing_input_ports=[llm.ports.messages_emit_input],
    )
    tools.ports.tools_output > llm.ports.tools_input
    llm.ports.tool_use_output > tools.ports.tool_use_input
    tools.ports.tool_use_output > gateway.ports.tool_use_input
    return gateway, llm, tools


@pytest.mark.parametrize("output_mode", ["stream", "atomic"])
@pytest.mark.asyncio
async def test_one_stream_carries_both_rounds(output_mode):
    gateway, llm, tools = _graph(
        [_lookup_call(), "Prednisone is on your list."], output_mode=output_mode,
    )
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("Is prednisone on my list?")
    events = [event async for event in turn.stream()]
    types = [event.type for event in events]

    assert types[-1] == "done"
    assert types.count("tool_calls_complete") == 1
    assert types.index("tool_calls_complete") < types.index("tool_results") < types.index("done")
    assert "".join(e.content_delta or "" for e in events if e.type == "token") == "Prednisone is on your list."
    results = next(e for e in events if e.type == "tool_results")
    assert results.tool_results[0]["status"] == "succeeded"
    assert results.tool_results[0]["model_tool_name"] == "lookup"

    final = await turn.final_message()
    assert final.model.content == "Prednisone is on your list."
    state = gateway.model.get_turn_state(turn.turn_id)
    assert state.done and state.rounds == 2

    first, second = llm.model.requests
    assert [m["role"] for m in first] == ["system", "user"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert second[2]["tool_calls"][0]["id"] == second[3]["tool_call_id"]
    assert json.loads(second[2]["tool_calls"][0]["function"]["arguments"]) == {"name": "prednisone"}
    assert second[3]["content"] == "prednisone: found"


@pytest.mark.asyncio
async def test_round_budget_denies_then_fails():
    # Round 1 may run tools. Round 2's calls are denied with a readable reason.
    # Round 3 still calls tools, so the turn fails.
    gateway, llm, tools = _graph(
        [_lookup_call("a"), _lookup_call("b"), _lookup_call("c"), "never reached"],
        output_mode="atomic", max_tool_rounds=1,
    )
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("look everything up")
    events = [event async for event in turn.stream()]
    types = [event.type for event in events]

    assert types[-1] == "error"
    assert "tool_round_budget_exhausted" in events[-1].error
    denied = [e for e in events if e.type == "tool_results"][1]
    assert denied.tool_results[0]["status"] == "denied"
    assert "budget" in denied.tool_results[0]["permission"]["reason"]
    third = llm.model.requests[2]
    assert third[-1]["role"] == "tool" and third[-1]["content"].startswith("Denied: Tool round budget")
    assert len(llm.model.requests) == 3


@pytest.mark.asyncio
async def test_cancel_during_tool_round_ends_the_stream():
    gateway, llm, tools = _graph([_lookup_call(), "late"], output_mode="atomic")
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("hi")
    turn.cancel()
    events = [event async for event in turn.stream()]
    assert [e.type for e in events] == ["cancelled"]
