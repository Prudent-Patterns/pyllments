from types import SimpleNamespace

import pytest

from pyllments.payloads.message.message_model import MessageModel


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
