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


def _graph(
    script, *, output_mode: str, max_tool_rounds: int = 6, max_tool_failures: int = 3, **gateway_args
):
    tools = ToolUseElement(name="tools", functions=[lookup], prefix_names=False)
    llm = LLMChatElement(backend="mock", output_mode=output_mode, script=script)
    history = HistoryHandlerElement(
        context_token_limit=8000, summary_token_threshold=0,
        projection_tiers={0: {}}, tokenizer_model="gpt-4o",
    )
    gateway = ChatGatewayElement(
        max_tool_rounds=max_tool_rounds, max_tool_failures=max_tool_failures, **gateway_args
    )
    gateway.ports.request_options_output > llm.ports.request_options_input

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
            "turn_notice": {"ports": [gateway.ports.turn_notice_output]},
        },
        trigger_map={
            "user_query": ["system_constant", "[history]", "user_query", "[turn_notice]"],
            "tool_results": ["system_constant", "history", "[turn_notice]"],
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

    # Every request ends with the turn notice; the rest is the conversation so far.
    first, second = llm.model.requests
    assert [m["role"] for m in first] == ["system", "user", "system"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool", "system"]
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
    assert third[-2]["role"] == "tool" and third[-2]["content"].startswith("Denied: Tool round budget")
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


@pytest.mark.asyncio
async def test_the_round_after_the_budget_runs_without_tools():
    gateway, llm, tools = _graph(
        [_lookup_call("a"), _lookup_call("b"), "done"], output_mode="atomic", max_tool_rounds=1,
    )
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("look things up")
    events = [event async for event in turn.stream()]

    # Once the budget is spent, every later request is made without tools.
    assert [args.get("tool_choice") for args in llm.model.request_args] == [None, "none", "none"]
    # The mock ignores tool_choice and calls again, so the fallback denial still applies.
    denied = [e for e in events if e.type == "tool_results"][1]
    assert denied.tool_results[0]["status"] == "denied"
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_three_failed_calls_end_the_tool_rounds():
    broken = {"content": "", "tool_calls": [
        {"name": "nope", "arguments": {}}, {"name": "nope", "arguments": {}}, {"name": "nope", "arguments": {}},
    ]}
    gateway, llm, tools = _graph([broken, "I could not look that up."], output_mode="atomic")
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("hi")
    events = [event async for event in turn.stream()]

    results = next(e for e in events if e.type == "tool_results")
    assert [r["status"] for r in results.tool_results] == ["failed"] * 3
    assert llm.model.request_args[1] == {"tool_choice": "none"}
    assert "Error: Unknown tool: nope" in llm.model.requests[1][-2]["content"]
    assert llm.model.requests[1][-1]["content"].startswith("Tool round 2 of 6; failed calls 3 of 3.")
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_a_provider_failure_ends_the_turn_with_an_error_event():
    gateway, llm, tools = _graph([_lookup_call(), {"error": "503 overloaded"}], output_mode="stream")
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("hi")
    events = [event async for event in turn.stream()]
    assert events[-1].type == "error"
    assert "503" in events[-1].error


@pytest.mark.asyncio
async def test_every_round_ends_with_a_notice_of_where_the_turn_stands():
    gateway, llm, tools = _graph(
        [_lookup_call("a"), _lookup_call("b"), "done"], output_mode="atomic", max_tool_rounds=2,
        turn_notice_template="Today is {{ date }}. Round {{ round }}/{{ max_rounds }}, failed "
        "{{ failures }}. {% if tools_allowed %}More later.{% else %}Words now.{% endif %}",
    )
    await tools.model.await_ready()
    await tools.ports.output["tools_output"].drain()

    turn = await gateway.submit_message_async("look things up", facts={"date": "2026-10-07"})
    async for _event in turn.stream():
        pass

    tails = [request[-1] for request in llm.model.requests]
    assert all(tail["role"] == "system" for tail in tails)
    assert [tail["content"] for tail in tails] == [
        "Today is 2026-10-07. Round 1/2, failed 0. More later.",
        "Today is 2026-10-07. Round 2/2, failed 0. More later.",
        "Today is 2026-10-07. Round 3/2, failed 0. Words now.",
    ]
    # The notice is the suffix: everything before it is the same request as last time.
    assert llm.model.requests[1][:-1][: len(llm.model.requests[0]) - 1] == llm.model.requests[0][:-1]

