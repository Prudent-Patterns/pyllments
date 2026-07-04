import asyncio

import pytest

from pyllments.elements import ChatGatewayElement, PipeElement, ToolUseElement
from pyllments.elements.tool_use.tool_invocation_context import ToolCancelled, ToolInvocationContext
from pyllments.payloads import StructuredPayload, ToolUsePayload


def test_payload_cancel_lifecycle():
    payload = ToolUsePayload(executor_element_name="main_tools")
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="secret",
        model_tool_name="functions_secret",
        permission_required=True,
    )
    payload.model.apply_permission_request([index])
    payload.model.cancel_call(index, reason="Superseded")
    assert payload.model.tool_calls[index]["status"] == "cancelled"
    assert payload.model.completed


def test_payload_orphaned_result():
    payload = ToolUsePayload(executor_element_name="main_tools")
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="add",
        model_tool_name="functions_add",
    )
    payload.model.attach_result(
        index,
        {"content": [{"type": "text", "text": "ok"}], "raw": None, "metadata": {}},
        orphaned=True,
    )
    assert payload.model.tool_calls[index]["status"] == "orphaned_completed"
    assert payload.model.tool_calls[index]["metadata"]["orphaned"] is True


@pytest.mark.asyncio
async def test_function_tool_context_not_in_schema():
    async def cooperative(value: str, context: ToolInvocationContext) -> str:
        return value

    element = ToolUseElement(name="main_tools", functions=[cooperative])
    await element.model.await_ready()

    spec = element.model.tool_specs["functions_cooperative"]
    assert "context" not in spec.parameters_schema.get("properties", {})


@pytest.mark.asyncio
async def test_function_tool_observes_cancellation():
    async def slow(value: str, context: ToolInvocationContext) -> str:
        for _ in range(20):
            context.throw_if_cancelled()
            await asyncio.sleep(0.01)
        return value

    element = ToolUseElement(name="main_tools", functions=[slow])
    await element.model.await_ready()

    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="slow",
        model_tool_name="functions_slow",
        parameters={"value": "x"},
    )
    payload.model.metadata["execution_owner"] = "branch-1"
    payload.bind_executor(element)

    task = asyncio.create_task(element.execute_tool_use_payload(payload))
    await asyncio.sleep(0.03)
    await element.cancel_execution_for_owner("branch-1")
    result = await task

    assert result.model.tool_calls[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_function_tool_error_flows_normally():
    def boom(value: str) -> str:
        raise RuntimeError("boom")

    element = ToolUseElement(name="main_tools", functions=[boom])
    await element.model.await_ready()

    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="boom",
        model_tool_name="functions_boom",
        parameters={"value": "x"},
    )
    payload.bind_executor(element)

    result = await element.execute_tool_use_payload(payload)
    assert result.model.tool_calls[0]["status"] == "failed"
    assert "boom" in result.model.tool_calls[0]["error"]["message"]


def _permission_tool_use_payload() -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="secret",
        model_tool_name="functions_secret",
        parameters={"value": "hidden"},
        permission_required=True,
    )
    for record in payload.model.tool_calls:
        record["status"] = "awaiting_permission"
    return payload


def _wire_gateway_tools(gateway, tool_use_el, result_pipe=None):
    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    if result_pipe is not None:
        gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input


@pytest.mark.asyncio
async def test_new_message_clears_pending_permission_reviews():
    def secret(value: str) -> str:
        return value

    tool_use_el = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    await tool_use_el.model.await_ready()

    reviews: list[dict] = []
    gateway = ChatGatewayElement(on_tool_use=lambda review: reviews.append(review) or None)
    tools_pipe = PipeElement(name="tools_pipe")
    _wire_gateway_tools(gateway, tool_use_el)

    tools_pipe.ports.output["pipe_output"] > gateway.ports.input["tool_use_input"]
    await gateway.submit_message_async("first")
    await gateway.ports.output["message_output"].drain()

    tools = _permission_tool_use_payload()
    await tools_pipe.async_send_payload(tools)

    assert len(reviews) == 1
    assert gateway.model.get_pending_tool_use(reviews[0]) is not None

    await gateway.submit_message_async("second")
    await gateway.ports.output["message_output"].drain()

    assert gateway.model.get_pending_tool_use(reviews[0]) is None
    assert gateway.model._pending_tool_uses == []


@pytest.mark.asyncio
async def test_gateway_suppresses_inactive_owner_results():
    gateway = ChatGatewayElement()
    result_pipe = PipeElement(name="result_pipe")
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input

    notices: list[dict] = []
    gateway.model.on_tool_result = lambda notice: notices.append(notice)

    gateway.model.begin_new_execution_branch()
    owner, _new_owner = gateway.model.begin_new_execution_branch()

    payload = ToolUsePayload(executor_element_name="main_tools")
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="add",
        model_tool_name="functions_add",
    )
    payload.model.attach_result(
        index,
        {"content": [{"type": "text", "text": "ok"}], "raw": None, "metadata": {}},
    )
    payload.model.metadata["execution_owner"] = owner

    await gateway._emit_tool_result_if_active(payload)
    await gateway.ports.output["tool_result_output"].drain()

    assert len(result_pipe.received_payloads) == 0
    assert notices and notices[0].get("orphaned") is True


@pytest.mark.asyncio
async def test_abort_branch_cancels_running_tools():
    started = asyncio.Event()

    async def slow_add(a: int, b: int, context: ToolInvocationContext) -> int:
        started.set()
        while True:
            context.throw_if_cancelled()
            await asyncio.sleep(0.05)

    tool_use_el = ToolUseElement(name="main_tools", functions=[slow_add])
    await tool_use_el.model.await_ready()

    gateway = ChatGatewayElement()
    owner = gateway.model.current_execution_owner()

    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="slow_add",
        model_tool_name="functions_slow_add",
        parameters={"a": 1, "b": 2},
    )
    payload.model.metadata["execution_owner"] = owner
    payload.bind_executor(tool_use_el)

    task = asyncio.create_task(tool_use_el.execute_tool_use_payload(payload))
    await asyncio.wait_for(started.wait(), timeout=2.0)
    await gateway._abort_branch_tool_work(owner, reason="Superseded by new user message")
    result = await asyncio.wait_for(task, timeout=2.0)

    assert result.model.tool_calls[0]["status"] == "cancelled"
