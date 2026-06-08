import asyncio
from types import SimpleNamespace

import pytest

from pyllments.elements.chat_gateway import ChatGatewayElement
from pyllments.elements.pipe import PipeElement
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

    await gateway.ports.output["message_output"].connect(user_pipe.ports.input["pipe_input"])

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assert turn.turn_id == "turn-1"
    assert len(user_pipe.received_payloads) == 1
    assert user_pipe.received_payloads[0].model.content == "Hello"
    assert user_pipe.received_payloads[0].model.correlation_id == "turn-1"


@pytest.mark.asyncio
async def test_turn_stream_receives_assistant_events():
    gateway = ChatGatewayElement()
    llm_pipe = PipeElement(name="llm_pipe")

    await llm_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["assistant_message_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assistant = MessagePayload(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
    )
    llm_pipe.send_payload(assistant)
    await llm_pipe.ports.output["pipe_output"].drain()

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

    await gateway.ports.output["tool_events_output"].connect(tool_pipe.ports.input["pipe_input"])
    await llm_pipe.ports.output["pipe_output"].connect(
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
    llm_pipe.send_payload(
        MessagePayload(role="assistant", mode="stream", message_coroutine=tool_stream())
    )
    await llm_pipe.ports.output["pipe_output"].drain()

    async for event in turn.stream():
        if event.type == "done":
            break

    await gateway.ports.output["tool_events_output"].drain()

    assert len(tool_pipe.received_payloads) == 1
    payload = tool_pipe.received_payloads[0]
    assert isinstance(payload, StructuredPayload)
    assert payload.model.data["turn_id"] == turn.turn_id
    assert payload.model.data["tool_calls"][0]["function"]["name"] == "lookup"


def _tool_use_payload(
    *,
    permission_required: bool = False,
    completed: bool = False,
    correlation_id: str | None = None,
) -> ToolUsePayload:
    payload = ToolUsePayload(
        executor_element_name="main_tools",
        correlation_id=correlation_id,
        turn_id=correlation_id,
    )
    payload.model.add_tool_use(
        adapter_name="mcp",
        provider_name="app_mcp",
        tool_name="delete_record",
        model_tool_name="app_mcp_delete_record",
        description="Delete a record",
        parameters={"id": "1"},
        permission_required=permission_required,
    )
    if completed:
        tool_use_id = next(iter(payload.model.tool_uses))
        payload.model.attach_result(
            tool_use_id,
            {"content": [{"type": "text", "text": "ok"}], "raw": None, "metadata": {}},
        )
    elif permission_required:
        for record in payload.model.tool_uses.values():
            record["status"] = "awaiting_permission"
    return payload


@pytest.mark.asyncio
async def test_completed_tool_use_invokes_hook_only():
    approved_pipe = PipeElement(name="approved_pipe")
    hook_calls: list[tuple[str, str]] = []

    def on_tool_use(payload, turn_id):
        hook_calls.append((turn_id, next(iter(payload.model.tool_uses))))

    gateway = ChatGatewayElement(on_tool_use=on_tool_use)
    tools_pipe = PipeElement(name="tools_pipe")
    await gateway.ports.output["tool_use_approved_output"].connect(
        approved_pipe.ports.input["pipe_input"]
    )
    await tools_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["tool_use_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    tools = _tool_use_payload(
        permission_required=False,
        completed=True,
        correlation_id=turn.turn_id,
    )
    tools_pipe.send_payload(tools)
    await tools_pipe.ports.output["pipe_output"].drain()
    await asyncio.sleep(0.05)

    assert len(hook_calls) == 1
    assert hook_calls[0][0] == turn.turn_id
    assert len(approved_pipe.received_payloads) == 0
    assert gateway.model.get_permission_request("perm-1") is None


@pytest.mark.asyncio
async def test_permission_required_creates_pending_request():
    permission_events: list[dict] = []

    def on_permission_request(event, turn_id):
        permission_events.append({**event, "turn_id_hook": turn_id})

    gateway = ChatGatewayElement(on_permission_request=on_permission_request)
    approved_pipe = PipeElement(name="approved_pipe")
    tools_pipe = PipeElement(name="tools_pipe")
    await gateway.ports.output["tool_use_approved_output"].connect(
        approved_pipe.ports.input["pipe_input"]
    )
    await tools_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["tool_use_input"]
    )

    turn = await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _tool_use_payload(permission_required=True, correlation_id=turn.turn_id)
    tools_pipe.send_payload(tools)
    await tools_pipe.ports.output["pipe_output"].drain()
    await asyncio.sleep(0.05)

    assert len(permission_events) == 1
    assert permission_events[0]["request_id"] == "perm-1"
    assert permission_events[0]["turn_id"] == turn.turn_id
    assert permission_events[0]["turn_id_hook"] == turn.turn_id
    assert permission_events[0]["tools"][0]["name"] == "app_mcp_delete_record"
    assert len(approved_pipe.received_payloads) == 0


@pytest.mark.asyncio
async def test_approve_permission_request_emits_payload():
    gateway = ChatGatewayElement()
    approved_pipe = PipeElement(name="approved_pipe")
    tools_pipe = PipeElement(name="tools_pipe")
    await gateway.ports.output["tool_use_approved_output"].connect(
        approved_pipe.ports.input["pipe_input"]
    )
    await tools_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["tool_use_input"]
    )

    turn = await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _tool_use_payload(permission_required=True, correlation_id=turn.turn_id)
    tools_pipe.send_payload(tools)
    await tools_pipe.ports.output["pipe_output"].drain()
    await asyncio.sleep(0.05)

    approved = await gateway.approve_permission_request("perm-1")
    await gateway.ports.output["tool_use_approved_output"].drain()

    assert approved is tools
    assert len(approved_pipe.received_payloads) == 1
    assert approved_pipe.received_payloads[0] is tools
    assert gateway.model.get_permission_request("perm-1") is None


@pytest.mark.asyncio
async def test_deny_permission_request_emits_tool_use_payload():
    gateway = ChatGatewayElement()
    denied_pipe = PipeElement(name="denied_pipe")
    tools_pipe = PipeElement(name="tools_pipe")
    await gateway.ports.output["tool_use_denied_output"].connect(
        denied_pipe.ports.input["pipe_input"]
    )
    await tools_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["tool_use_input"]
    )

    turn = await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    tools = _tool_use_payload(permission_required=True, correlation_id=turn.turn_id)
    tools_pipe.send_payload(tools)
    await tools_pipe.ports.output["pipe_output"].drain()
    await asyncio.sleep(0.05)

    denial = await gateway.deny_permission_request("perm-1", reason="User declined")
    await gateway.ports.output["tool_use_denied_output"].drain()

    assert isinstance(denial, ToolUsePayload)
    assert denial.model.metadata.get("denial_reason") == "User declined"
    assert len(denied_pipe.received_payloads) == 1
    assert denied_pipe.received_payloads[0].model.status == "completed"


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
    await llm_pipe.ports.output["pipe_output"].connect(
        gateway.ports.input["assistant_message_input"]
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output["message_output"].drain()

    assistant = MessagePayload(role="assistant", content="Hi", mode="atomic")
    assistant.model.ready = True
    llm_pipe.send_payload(assistant)
    await llm_pipe.ports.output["pipe_output"].drain()
    await asyncio.sleep(0.05)

    assert hook_turns == [turn.turn_id]
