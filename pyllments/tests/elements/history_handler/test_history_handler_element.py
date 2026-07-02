"""Tests for HistoryHandlerElement port behavior and deterministic receive handling."""

from __future__ import annotations

import asyncio

import pytest

from pyllments.elements import HistoryHandlerElement
from pyllments.elements.pipe import PipeElement
from pyllments.payloads import MessagePayload


@pytest.mark.asyncio
async def test_payload_input_loads_before_receive_returns():
    history_el = HistoryHandlerElement()
    received_contexts: list[list] = []

    async def capture_context(context: list) -> list:
        received_contexts.append(context)
        return context

    history_el.ports.output["context_output"].pack_payload_callback = capture_context

    sender = PipeElement()
    sender.ports.output["pipe_output"] > history_el.ports.payload_input

    msg = MessagePayload(role="user", content="hello", mode="atomic")
    await sender.ports.output["pipe_output"].stage_emit(payload=msg)

    assert len(history_el.model.history) == 1
    assert history_el.model.history[0].payload.model.content == "hello"
    assert received_contexts == []


@pytest.mark.asyncio
async def test_payload_emit_input_emits_after_ingest():
    history_el = HistoryHandlerElement()
    received_contexts: list[list] = []

    async def capture_context(context: list) -> list:
        received_contexts.append(context)
        return context

    history_el.ports.output["context_output"].pack_payload_callback = capture_context

    sender = PipeElement()
    sender.ports.output["pipe_output"] > history_el.ports.payload_emit_input

    msg = MessagePayload(role="user", content="emit me", mode="atomic")
    await sender.ports.output["pipe_output"].stage_emit(payload=msg)

    assert len(history_el.model.history) == 1
    assert len(received_contexts) == 1
    assert len(received_contexts[0]) == 1
    assert received_contexts[0][0].model.content == "emit me"


@pytest.mark.asyncio
async def test_payload_pre_emit_input_emits_prior_context_then_stores():
    history_el = HistoryHandlerElement()
    received_contexts: list[list] = []

    async def capture_context(context: list) -> list:
        received_contexts.append(list(context))
        return context

    history_el.ports.output["context_output"].pack_payload_callback = capture_context

    sender = PipeElement()
    sender.ports.output["pipe_output"] > history_el.ports.payload_pre_emit_input

    first = MessagePayload(role="user", content="first", mode="atomic")
    await sender.ports.output["pipe_output"].stage_emit(payload=first)

    assert len(received_contexts) == 1
    assert received_contexts[0] == []
    assert len(history_el.model.history) == 1

    second = MessagePayload(role="user", content="second", mode="atomic")
    await sender.ports.output["pipe_output"].stage_emit(payload=second)

    assert len(received_contexts) == 2
    assert len(received_contexts[1]) == 1
    assert received_contexts[1][0].model.content == "first"
    assert len(history_el.model.history) == 2


@pytest.mark.asyncio
async def test_ordered_fanout_waits_for_first_receiver_before_history():
    """History payload_input should see a ready payload after an active consumer."""
    history_el = HistoryHandlerElement()
    consumer_done = asyncio.Event()

    async def active_consumer(payload: MessagePayload):
        await payload.model.aget_message()
        consumer_done.set()

    consumer = PipeElement()
    consumer.ports.add_input(
        name="consumer_input",
        unpack_payload_callback=active_consumer,
    )

    sender = PipeElement()
    out = sender.ports.output["pipe_output"]
    out > consumer.ports.input["consumer_input"]
    out > history_el.ports.payload_input

    msg = MessagePayload(
        role="assistant",
        content="streamed reply",
        mode="atomic",
    )

    await out.stage_emit(payload=msg)

    assert consumer_done.is_set()
    assert len(history_el.model.history) == 1
    assert history_el.model.history[0].payload.model.content == "streamed reply"
