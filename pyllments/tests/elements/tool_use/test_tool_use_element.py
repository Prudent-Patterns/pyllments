import pytest

from pyllments.elements import ChatGatewayElement, PipeElement, ToolUseElement
from pyllments.payloads import StructuredPayload, ToolUsePayload


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def secret(value: str) -> str:
    """Access secret data."""
    return value


@pytest.mark.asyncio
async def test_function_tools_schema():
    element = ToolUseElement(functions=[add])
    pipe = PipeElement(name="schema_pipe")

    element.ports.tools_schema_output > pipe.ports.pipe_input
    await element.model.await_ready()
    await element.ports.output["tools_schema_output"].drain()

    assert "functions_add" in element.model.tool_specs
    assert len(pipe.received_payloads) > 0
    assert pipe.received_payloads[0].model.schema is not None


@pytest.mark.asyncio
async def test_tool_use_payload_is_bound_on_creation():
    element = ToolUseElement(name="main_tools", functions=[add])
    tool_use_pipe = PipeElement(name="tool_use_pipe")
    request_pipe = PipeElement(name="request_pipe")

    element.ports.tool_use_output > tool_use_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    await element.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_add", "parameters": {"a": 1, "b": 2}}])
    )
    await element.ports.output["tool_use_output"].drain()

    assert len(tool_use_pipe.received_payloads) == 1
    payload = tool_use_pipe.received_payloads[0]
    assert payload.is_bound
    assert payload.model.executor_element_name == "main_tools"


@pytest.mark.asyncio
async def test_tool_use_element_does_not_auto_execute():
    element = ToolUseElement(functions=[add])
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")

    element.ports.tool_result_output > result_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    await element.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_add", "parameters": {"a": 1, "b": 2}}])
    )
    await element.ports.output["tool_use_output"].drain()

    assert len(result_pipe.received_payloads) == 0


@pytest.mark.asyncio
async def test_execute_tool_use_payload_selected_records():
    element = ToolUseElement(functions=[add])
    await element.model.await_ready()

    payload = ToolUsePayload(executor_element_name=element.name)
    index = payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="add",
        model_tool_name="functions_add",
        parameters={"a": 2, "b": 3},
    )
    payload.bind_executor(element)

    executed = await element.execute_tool_use_payload(payload, tool_call_indices=[index])
    assert executed.model.tool_calls[index]["status"] == "succeeded"
    assert "5" in executed.model.content


@pytest.mark.asyncio
async def test_message_tool_calls_create_tool_use_payload():
    from pyllments.payloads import MessagePayload

    element = ToolUseElement(name="main_tools", functions=[add])
    tool_use_pipe = PipeElement(name="tool_use_pipe")
    message_pipe = PipeElement(name="message_pipe")
    element.ports.tool_use_output > tool_use_pipe.ports.pipe_input
    message_pipe.ports.pipe_output > element.ports.tool_request_message_input

    await element.model.await_ready()
    message = MessagePayload(
        role="assistant",
        mode="atomic",
        tool_calls=[
            {
                "id": "call_provider_123",
                "type": "function",
                "function": {"name": "functions_add", "arguments": '{"a": 1, "b": 2}'},
            }
        ],
    )
    message.model.ready = True
    await message_pipe.async_send_payload(message)
    await element.ports.output["tool_use_output"].drain()

    payload = tool_use_pipe.received_payloads[0]
    assert len(payload.model.tool_calls) == 1
    assert payload.model.tool_calls[0]["model_tool_name"] == "functions_add"
    assert payload.model.tool_calls[0]["parameters"] == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_permission_gating_emits_without_execution():
    element = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    tool_use_pipe = PipeElement(name="tool_use_pipe")
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")

    element.ports.tool_use_output > tool_use_pipe.ports.pipe_input
    element.ports.tool_result_output > result_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    await element.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_secret", "parameters": {"value": "hidden"}}])
    )
    await element.ports.output["tool_use_output"].drain()

    assert len(tool_use_pipe.received_payloads) == 1
    payload = tool_use_pipe.received_payloads[0]
    assert payload.model.needs_permission()
    assert payload.model.status == "awaiting_permission"
    assert len(result_pipe.received_payloads) == 0
