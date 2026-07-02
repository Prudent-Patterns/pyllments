import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyllments.elements import ChatGatewayElement, PipeElement, ToolUseElement
from pyllments.elements.chat_gateway.pending_tool_use_store import SQLitePendingToolUseStore
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload


def _chunk(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    tool_calls=None,
                )
            )
        ]
    )


async def _stream_chunks():
    yield _chunk("Hi ")
    yield _chunk("there")


@pytest.mark.asyncio
async def test_submit_message_emits_user_payload():
    gateway = ChatGatewayElement()
    user_pipe = PipeElement(name="user_pipe")

    gateway.ports.output["message_output"].connect(user_pipe.ports.input["pipe_input"])

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assert turn.turn_id == "turn-1"
    assert len(user_pipe.received_payloads) == 1
    assert user_pipe.received_payloads[0].model.content == "Hello"


@pytest.mark.asyncio
async def test_turn_stream_receives_assistant_events():
    gateway = ChatGatewayElement()
    llm_pipe = PipeElement(name="llm_pipe")

    llm_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["assistant_message_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assistant = MessagePayload(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
    )
    await llm_pipe.async_send_payload(assistant)

    events = [event async for event in turn.stream()]

    assert [e.type for e in events] == ["token", "token", "done"]
    final = await turn.final_message()
    assert final.model.content == "Hi there"


@pytest.mark.asyncio
async def test_cancel_turn_before_assistant_arrives():
    gateway = ChatGatewayElement()
    turn = gateway.submit_message("Hello")

    turn.cancel()

    assert gateway.model.is_turn_cancelled(turn.turn_id)

    assistant = MessagePayload(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
    )
    gateway.model.match_turn(assistant)
    assert assistant.model.cancelled is True


@pytest.mark.asyncio
async def test_fifo_turn_matching():
    gateway = ChatGatewayElement()
    model = gateway.model

    first = gateway.submit_message("one")
    second = gateway.submit_message("two")

    assistant_b = MessagePayload(role="assistant", content="B", mode="atomic")
    assistant_b.model.ready = True
    matched = model.match_turn(assistant_b)

    assert matched == first.turn_id
    assert model.get_turn_state(first.turn_id).assistant_message is assistant_b
    assert model.get_turn_state(second.turn_id).assistant_message is None


@pytest.mark.asyncio
async def test_tool_events_output_on_tool_calls_complete():
    gateway = ChatGatewayElement()
    tool_pipe = PipeElement(name="tool_pipe")
    llm_pipe = PipeElement(name="llm_pipe")

    gateway.ports.output["tool_events_output"].connect(tool_pipe.ports.input["pipe_input"])
    llm_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["assistant_message_input"]
    )

    def _tool_chunk(name: str, arguments: str):
        tc = SimpleNamespace(
            index=0,
            id="c1",
            type="function",
            function=SimpleNamespace(name=name, arguments=arguments),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))]
        )

    async def tool_stream():
        yield _tool_chunk("lookup", "{}")

    turn = await gateway.submit_message_async("tools?")
    await gateway.ports.output["message_output"].drain()
    await llm_pipe.async_send_payload(
        MessagePayload(role="assistant", mode="stream", message_coroutine=tool_stream())
    )

    async for event in turn.stream():
        if event.type == "done":
            break

    await gateway.ports.output["tool_events_output"].drain()

    assert len(tool_pipe.received_payloads) == 1
    payload = tool_pipe.received_payloads[0]
    assert isinstance(payload, StructuredPayload)
    assert payload.model.data["tool_calls"][0]["function"]["name"] == "lookup"


def _tool_use_payload(
    *,
    permission_required: bool = False,
    completed: bool = False,
    executor_element_name: str = "main_tools",
) -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name=executor_element_name)
    index = payload.model.add_tool_call(
        adapter_name="mcp",
        provider_name="app_mcp",
        tool_name="delete_record",
        model_tool_name="app_mcp_delete_record",
        description="Delete a record",
        parameters={"id": "1"},
        permission_required=permission_required,
    )
    if completed:
        payload.model.attach_result(
            index,
            {"content": [{"type": "text", "text": "ok"}], "raw": None, "metadata": {}},
        )
    elif permission_required:
        payload.model.tool_calls[index]["status"] = "awaiting_permission"
    return payload


def _mixed_tool_use_payload() -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="add",
        model_tool_name="functions_add",
        parameters={"a": 1, "b": 2},
        permission_required=False,
    )
    payload.model.add_tool_call(
        adapter_name="mcp",
        provider_name="app_mcp",
        tool_name="delete_record",
        model_tool_name="app_mcp_delete_record",
        parameters={"id": "1"},
        permission_required=True,
    )
    for record in payload.model.tool_calls:
        if record.get("permission_required"):
            record["status"] = "awaiting_permission"
    return payload


def _permission_tool_use_payload() -> ToolUsePayload:
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="secret",
        model_tool_name="functions_secret",
        description="Access secret data",
        parameters={"value": "hidden"},
        permission_required=True,
    )
    for record in payload.model.tool_calls:
        record["status"] = "awaiting_permission"
    return payload


@pytest.fixture
def permission_tool_stack():
    async def _build():
        def secret(value: str) -> str:
            return value

        tool_use_el = ToolUseElement(
            name="main_tools",
            functions=[secret],
            tools_requiring_permission=["secret"],
        )
        await tool_use_el.model.await_ready()
        return tool_use_el

    return _build


@pytest.fixture
def tool_stack():
    async def _build():
        def add(a: int, b: int) -> int:
            return a + b

        tool_use_el = ToolUseElement(name="main_tools", functions=[add])
        await tool_use_el.model.await_ready()
        return tool_use_el

    return _build


@pytest.mark.asyncio
async def test_completed_tool_use_invokes_hook_only():
    result_pipe = PipeElement(name="result_pipe")
    hook_calls: list[list[str]] = []

    def on_tool_use(notice):
        hook_calls.append([tool.name for tool in notice.tools])

    gateway = ChatGatewayElement(on_tool_use=on_tool_use)
    gateway.ports.output["tool_result_output"].connect(result_pipe.ports.input["pipe_input"])
    tools_pipe = PipeElement(name="tools_pipe")
    tools_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["tool_use_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    tools = _tool_use_payload(permission_required=False, completed=True)
    await tools_pipe.async_send_payload(tools)
    await gateway.ports.output["tool_result_output"].drain()

    assert len(hook_calls) == 1
    assert hook_calls[0] == ["app_mcp_delete_record"]
    assert len(result_pipe.received_payloads) == 0
    assert gateway.model._permission_requests == []


@pytest.mark.asyncio
async def test_no_permission_tool_use_auto_executes(tool_stack):
    tool_use_el = await tool_stack()

    gateway = ChatGatewayElement()
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.output["pipe_output"] > tool_use_el.ports.tool_request_structured_input

    turn = await gateway.submit_message_async("run tool")
    await gateway.ports.output["message_output"].drain()

    await tools_pipe.async_send_payload(
        StructuredPayload(data=[{"name": "functions_add", "parameters": {"a": 2, "b": 3}}])
    )
    await tool_use_el.ports.output["tool_use_output"].drain()
    await gateway.ports.output["tool_result_output"].drain()

    assert len(result_pipe.received_payloads) == 1
    payload = result_pipe.received_payloads[0]
    assert any(record.get("status") == "succeeded" for record in payload.model.tool_calls)
    assert "5" in payload.model.content


@pytest.mark.asyncio
async def test_mixed_tool_use_executes_no_permission_and_waits_for_rest(tool_stack):
    tool_use_el = await tool_stack()

    permission_requests = []
    tool_notices: list[list[str]] = []
    gateway = ChatGatewayElement(
        on_tool_use=lambda notice: tool_notices.append([tool.name for tool in notice.tools]),
        on_permission_request=lambda request: permission_requests.append(request),
    )
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.output["pipe_output"] > gateway.ports.input["tool_use_input"]

    await gateway.submit_message_async("mixed")
    await gateway.ports.output["message_output"].drain()

    payload = _mixed_tool_use_payload()
    await tools_pipe.async_send_payload(payload)
    await gateway.ports.output["tool_result_output"].drain()

    assert len(result_pipe.received_payloads) == 1
    executed = result_pipe.received_payloads[0]
    ping_index = next(
        index
        for index, record in enumerate(executed.model.tool_calls)
        if record["model_tool_name"] == "functions_add"
    )
    delete_index = next(
        index
        for index, record in enumerate(executed.model.tool_calls)
        if record["model_tool_name"] == "app_mcp_delete_record"
    )
    assert executed.model.tool_calls[ping_index]["status"] == "succeeded"
    assert executed.model.tool_calls[delete_index]["status"] == "awaiting_permission"
    assert tool_notices == [["functions_add", "app_mcp_delete_record"]]
    assert len(permission_requests) == 1
    assert [tool.name for tool in permission_requests[0].tools] == ["app_mcp_delete_record"]


@pytest.mark.asyncio
async def test_permission_required_creates_pending_request(permission_tool_stack):
    tool_use_el = await permission_tool_stack()

    permission_requests = []

    def on_permission_request(request):
        permission_requests.append(request)

    gateway = ChatGatewayElement(on_permission_request=on_permission_request)
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.output["pipe_output"] > gateway.ports.input["tool_use_input"]

    await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _permission_tool_use_payload()
    await tools_pipe.async_send_payload(tools)
    await gateway.ports.output["tool_result_output"].drain()

    assert len(permission_requests) == 1
    assert [tool.name for tool in permission_requests[0].tools] == ["functions_secret"]
    assert permission_requests[0].tools[0].parameters == {"value": "hidden"}
    assert len(result_pipe.received_payloads) == 0


@pytest.mark.asyncio
async def test_permission_request_object_approval_executes_and_emits(permission_tool_stack):
    tool_use_el = await permission_tool_stack()

    permission_requests = []
    gateway = ChatGatewayElement()
    gateway.model.on_permission_request = lambda request: permission_requests.append(request)
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.output["pipe_output"] > gateway.ports.input["tool_use_input"]

    await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _permission_tool_use_payload()
    await tools_pipe.async_send_payload(tools)

    request = permission_requests[0]
    request.approve_all()
    approved = await gateway.resolve_permission_request(request)
    await gateway.ports.output["tool_result_output"].drain()

    assert approved is tools
    assert len(result_pipe.received_payloads) == 1
    assert any(record.get("status") == "succeeded" for record in approved.model.tool_calls)
    assert gateway.model._permission_requests == []


@pytest.mark.asyncio
async def test_permission_request_object_denial_emits_tool_use_payload(permission_tool_stack):
    tool_use_el = await permission_tool_stack()

    permission_requests = []
    gateway = ChatGatewayElement()
    gateway.model.on_permission_request = lambda request: permission_requests.append(request)
    result_pipe = PipeElement(name="result_pipe")
    tools_pipe = PipeElement(name="tools_pipe")

    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    gateway.ports.output["tool_result_output"] > result_pipe.ports.pipe_input
    tools_pipe.ports.output["pipe_output"] > gateway.ports.input["tool_use_input"]

    await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _permission_tool_use_payload()
    await tools_pipe.async_send_payload(tools)

    request = permission_requests[0]
    request.deny_all(reason="User declined")
    denial = await gateway.resolve_permission_request(request)
    await gateway.ports.output["tool_result_output"].drain()

    assert isinstance(denial, ToolUsePayload)
    assert denial.model.tool_calls[0]["permission"]["reason"] == "User declined"
    assert len(result_pipe.received_payloads) == 1
    assert result_pipe.received_payloads[0].model.status == "completed"


@pytest.mark.asyncio
async def test_hooks_support_async_callbacks():
    events: list[str] = []

    async def on_user_message_submitted(payload, turn_id):
        await asyncio.sleep(0)
        events.append(f"user:{turn_id}")

    gateway = ChatGatewayElement(on_user_message_submitted=on_user_message_submitted)
    await gateway.submit_message_async("Hi")
    await gateway.ports.output["message_output"].drain()
    await asyncio.sleep(0.05)

    assert events == ["user:turn-1"]


@pytest.mark.asyncio
async def test_on_assistant_message_hook():
    hook_turns: list[str] = []

    def on_assistant_message(payload, turn_id):
        hook_turns.append(turn_id)

    gateway = ChatGatewayElement(on_assistant_message=on_assistant_message)
    llm_pipe = PipeElement(name="llm_pipe")
    llm_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["assistant_message_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assistant = MessagePayload(role="assistant", content="Hi", mode="atomic")
    assistant.model.ready = True
    await llm_pipe.async_send_payload(assistant)
    await asyncio.sleep(0.05)

    assert hook_turns == [turn.turn_id]
