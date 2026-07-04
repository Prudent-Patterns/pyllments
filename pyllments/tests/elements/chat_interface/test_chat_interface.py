import pytest

from pyllments.elements import ChatInterfaceElement, PipeElement, ToolUseElement
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload


def stream_chat_interface_test():
    chat_interface_element = ChatInterfaceElement()

    def word_generator(sentence):
        words = sentence.split()
        for word in words:
            yield word

    stream = word_generator("my name is llm shady")

    new_payload  = MessagePayload(mode='stream')
    new_payload.model.stream_obj = stream
    
    chat_interface_element.model.new_message = new_payload
    
    assert chat_interface_element.model.message_list[0] is new_payload


def _permission_payload() -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="secret",
        model_tool_name="functions_secret",
        parameters={"value": "hidden"},
        permission_required=True,
    )
    return payload


@pytest.mark.asyncio
async def test_tool_use_input_displays_pending_without_awaiting_completion():
    chat_interface = ChatInterfaceElement()
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    chat_interface.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.pipe_output > chat_interface.ports.input["tool_use_input"]

    payload = _permission_payload()
    await tools_pipe.async_send_payload(payload)

    assert chat_interface.model.message_list[-1] is payload
    assert payload.model.status == "awaiting_permission"
    assert chat_interface.model.find_pending_tool_use(payload) is not None
    assert result_pipe.received_payloads == []


@pytest.mark.asyncio
async def test_no_permission_tool_use_executes_directly_from_payload():
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    tool_use_el = ToolUseElement(name="main_tools", functions=[add])
    chat_interface = ChatInterfaceElement()
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")

    request_pipe.ports.pipe_output > tool_use_el.ports.tool_request_structured_input
    tool_use_el.ports.tool_use_output > chat_interface.ports.tool_use_input
    chat_interface.ports.tool_result_output > result_pipe.ports.pipe_input

    await tool_use_el.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_add", "parameters": {"a": 2, "b": 3}}])
    )

    assert len(result_pipe.received_payloads) == 1
    payload = result_pipe.received_payloads[0]
    assert payload.model.completed
    assert payload.model.tool_calls[0]["status"] == "succeeded"
    assert "5" in payload.model.content


@pytest.mark.asyncio
async def test_permission_tool_use_waits_for_approval_then_executes():
    def secret(value: str) -> str:
        """Return secret data."""
        return value

    tool_use_el = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    chat_interface = ChatInterfaceElement()
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")

    request_pipe.ports.pipe_output > tool_use_el.ports.tool_request_structured_input
    tool_use_el.ports.tool_use_output > chat_interface.ports.tool_use_input
    chat_interface.ports.tool_result_output > result_pipe.ports.pipe_input

    await tool_use_el.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_secret", "parameters": {"value": "hidden"}}])
    )

    payload = chat_interface.model.message_list[-1]
    assert payload.model.status == "awaiting_permission"
    assert result_pipe.received_payloads == []

    await chat_interface.approve_tool_use(payload)

    assert len(result_pipe.received_payloads) == 1
    assert payload.model.completed
    assert payload.model.tool_calls[0]["status"] == "succeeded"
    assert "hidden" in payload.model.content


@pytest.mark.asyncio
async def test_permission_tool_use_denial_emits_without_execution():
    calls = []

    def secret(value: str) -> str:
        """Return secret data."""
        calls.append(value)
        return value

    tool_use_el = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    chat_interface = ChatInterfaceElement()
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")

    request_pipe.ports.pipe_output > tool_use_el.ports.tool_request_structured_input
    tool_use_el.ports.tool_use_output > chat_interface.ports.tool_use_input
    chat_interface.ports.tool_result_output > result_pipe.ports.pipe_input

    await tool_use_el.model.await_ready()
    await request_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_secret", "parameters": {"value": "hidden"}}])
    )

    payload = chat_interface.model.message_list[-1]
    await chat_interface.deny_tool_use(payload, reason="not now")

    assert calls == []
    assert len(result_pipe.received_payloads) == 1
    assert payload.model.completed
    assert payload.model.tool_calls[0]["status"] == "denied"
    assert "not now" in payload.model.content


@pytest.mark.asyncio
async def test_new_user_message_cancels_pending_tool_uses():
    chat_interface = ChatInterfaceElement()
    tools_pipe = PipeElement(name="tools_pipe")
    tools_pipe.ports.pipe_output > chat_interface.ports.input["tool_use_input"]

    payload = _permission_payload()
    await tools_pipe.async_send_payload(payload)

    assert chat_interface.model.find_pending_tool_use(payload) is not None

    await chat_interface._prepare_new_user_message()

    assert chat_interface.model.find_pending_tool_use(payload) is None
    assert payload.model.completed
    assert payload.model.tool_calls[0]["status"] == "cancelled"