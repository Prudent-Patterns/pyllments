import asyncio
from types import SimpleNamespace

import pytest

from pyllments.payloads.message.message_model import MessageModel
from pyllments.payloads.message.stream_events import MessageStreamEvent


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
    yield _chunk("Hello ")
    yield _chunk("world")


async def _build_stream():
    return _stream_chunks()


@pytest.mark.asyncio
async def test_stream_accepts_coroutine_that_resolves_to_async_iterator():
    model = MessageModel(
        role="assistant",
        mode="stream",
        message_coroutine=_build_stream(),
    )

    await model.stream()

    assert model.content == "Hello world"
    assert model.streamed is True
    assert model.ready is True
    assert hasattr(model.message_coroutine, "__aiter__")


@pytest.mark.asyncio
async def test_aiter_events_yields_tokens():
    model = MessageModel(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
    )

    events = [event async for event in model.aiter_events()]

    assert [e.type for e in events] == ["token", "token", "done"]
    assert events[0].content_delta == "Hello "
    assert events[1].content_delta == "world"
    assert model.content == "Hello world"


@pytest.mark.asyncio
async def test_aiter_events_without_aggregation():
    model = MessageModel(
        role="assistant",
        mode="stream",
        message_coroutine=_stream_chunks(),
        aggregate_stream=False,
    )

    async for _event in model.aiter_events():
        pass

    assert model.content == ""
    assert model.streamed is True


def _tool_chunk(name: str, arguments: str, chunk_id: str = "call_1"):
    tc = SimpleNamespace(
        index=0,
        id=chunk_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[tc]))]
    )


async def _tool_stream():
    yield _tool_chunk("get_weather", '{"loc":')
    yield _tool_chunk("", ' "NYC"}', chunk_id="")


@pytest.mark.asyncio
async def test_aiter_events_tool_call_deltas_and_complete():
    model = MessageModel(
        role="assistant",
        mode="stream",
        message_coroutine=_tool_stream(),
    )

    events = [event async for event in model.aiter_events()]
    types = [e.type for e in events]

    assert "tool_call_delta" in types
    assert "tool_calls_complete" in types
    assert types[-1] == "done"
    assert model.tool_calls[0]["function"]["name"] == "get_weather"


async def _slow_stream():
    yield _chunk("Hello ")
    await asyncio.sleep(0.05)
    yield _chunk("world")


@pytest.mark.asyncio
async def test_cancel_stops_stream_early():
    model = MessageModel(
        role="assistant",
        mode="stream",
        message_coroutine=_slow_stream(),
    )

    collected = []

    async def consume():
        async for event in model.aiter_events():
            collected.append(event.type)
            if event.type == "token":
                model.cancel()
                break

    await consume()

    assert model.cancelled is True
    assert "token" in collected
