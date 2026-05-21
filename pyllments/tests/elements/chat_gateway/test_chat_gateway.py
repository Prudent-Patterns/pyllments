import asyncio
from types import SimpleNamespace

import pytest

from pyllments.elements.chat_gateway import ChatGatewayElement
from pyllments.elements.pipe import PipeElement
from pyllments.payloads import MessagePayload, StructuredPayload


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

    await gateway.ports.output['message_output'].connect(user_pipe.ports.input['pipe_input'])

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output['message_output'].drain()

    assert turn.turn_id == "turn-1"
    assert len(user_pipe.received_payloads) == 1
    assert user_pipe.received_payloads[0].model.content == "Hello"
    assert user_pipe.received_payloads[0].model.correlation_id == "turn-1"


@pytest.mark.asyncio
async def test_turn_stream_receives_assistant_events():
    gateway = ChatGatewayElement()
    llm_pipe = PipeElement(name="llm_pipe")

    await llm_pipe.ports.output['pipe_output'].connect(
        gateway.ports.input['assistant_message_input']
    )

    turn = await gateway.submit_message_async("Hello")
    await gateway.ports.output['message_output'].drain()

    assistant = MessagePayload(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
    )
    llm_pipe.send_payload(assistant)
    await llm_pipe.ports.output['pipe_output'].drain()

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

    await gateway.ports.output['tool_events_output'].connect(tool_pipe.ports.input['pipe_input'])
    await llm_pipe.ports.output['pipe_output'].connect(
        gateway.ports.input['assistant_message_input']
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
    await gateway.ports.output['message_output'].drain()
    llm_pipe.send_payload(
        MessagePayload(role="assistant", mode="stream", message_coroutine=tool_stream())
    )
    await llm_pipe.ports.output['pipe_output'].drain()

    async for event in turn.stream():
        if event.type == "done":
            break

    await gateway.ports.output['tool_events_output'].drain()

    assert len(tool_pipe.received_payloads) == 1
    payload = tool_pipe.received_payloads[0]
    assert isinstance(payload, StructuredPayload)
    assert payload.model.data["turn_id"] == turn.turn_id
    assert payload.model.data["tool_calls"][0]["function"]["name"] == "lookup"
