import pytest

from pyllments.payloads import ToolUsePayload
from pyllments.payloads.tool_use import ToolUseExecutorNotBoundError


class _StubExecutor:
    name = "main_tools"

    def __init__(self):
        self.calls: list[list[int] | None] = []

    async def execute_tool_use_payload(self, payload, tool_call_indices=None):
        self.calls.append(tool_call_indices)
        payload.model.attach_result(
            0,
            {"content": [{"type": "text", "text": "pong"}], "raw": None, "metadata": {}},
        )
        return payload


def test_tool_use_payload_lifecycle():
    payload = ToolUsePayload(executor_element_name="main_tools")
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
        parameters={"x": 1},
        permission_required=True,
    )
    assert payload.model.needs_permission()
    payload.model.apply_permission_request()
    assert payload.model.tool_calls[index]["status"] == "awaiting_permission"

    payload.model.approve()
    assert payload.model.can_execute(index)
    payload.model.attach_result(
        index,
        {"content": [{"type": "text", "text": "pong"}], "raw": None, "metadata": {}},
    )
    assert payload.model.completed
    assert "pong" in payload.model.content


def test_tool_use_payload_denial():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="mcp",
        provider_name="fs",
        tool_name="delete",
        model_tool_name="fs_delete",
        permission_required=True,
    )
    payload.model.deny(reason="nope")
    assert payload.model.completed
    assert "denied" in payload.model.content.lower() or payload.model.status == "completed"


@pytest.mark.asyncio
async def test_tool_use_payload_binding_and_execution():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
        parameters={"x": 1},
    )
    executor = _StubExecutor()
    payload.bind_executor(executor)
    assert payload.is_bound

    result = await payload.execute_approved()
    assert len(executor.calls) == 1
    assert result.model.completed
    assert "pong" in result.model.content


@pytest.mark.asyncio
async def test_tool_use_payload_registry_auto_rebind_on_execute():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
        parameters={"x": 1},
    )
    executor = _StubExecutor()
    ToolUsePayload.register_executor(executor)

    result = await payload.execute_approved()
    assert payload.is_bound
    assert len(executor.calls) == 1
    assert "pong" in result.model.content

    ToolUsePayload.unregister_executor("main_tools")


@pytest.mark.asyncio
async def test_tool_use_payload_bind_registered_executor():
    payload = ToolUsePayload(executor_element_name="registry_tools")
    executor = _StubExecutor()
    executor.name = "registry_tools"
    ToolUsePayload.register_executor(executor)

    assert payload.bind_registered_executor()
    assert payload.is_bound

    ToolUsePayload.unregister_executor("registry_tools")


@pytest.mark.asyncio
async def test_tool_use_payload_unbound_execution_raises():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
    )
    with pytest.raises(ToolUseExecutorNotBoundError):
        await payload.execute_approved()


@pytest.mark.asyncio
async def test_tool_use_payload_selected_execution():
    payload = ToolUsePayload(executor_element_name="main_tools")
    first = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="a",
        model_tool_name="functions_a",
    )
    second = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="b",
        model_tool_name="functions_b",
    )
    executor = _StubExecutor()
    payload.bind_executor(executor)

    await payload.execute_approved(tool_call_indices=[first])
    assert executor.calls == [[first]]
    assert payload.model.tool_calls[first]["status"] == "succeeded"
    assert payload.model.tool_calls[second]["status"] == "approved"


def test_tool_calls_are_list_without_generated_ids():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
    )
    assert isinstance(payload.model.tool_calls, list)
    assert "tool_use_id" not in payload.model.tool_calls[0]
    assert "payload_id" not in payload.param
    assert "correlation_id" not in payload.param
