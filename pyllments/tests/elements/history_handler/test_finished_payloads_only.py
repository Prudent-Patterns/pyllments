"""The ledger takes finished payloads only; the gateway is the uptake that finishes a reply."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyllments.elements import ChatGatewayElement, HistoryHandlerElement, PipeElement
from pyllments.elements.history_handler import UnfinishedPayloadError
from pyllments.elements.history_handler.history_store import SQLiteHistoryStore
from pyllments.payloads import MessagePayload, ToolUsePayload


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])


async def _stream():
    yield _chunk("Hello ")
    yield _chunk("world")


def _history(store=None):
    return HistoryHandlerElement(
        context_token_limit=8000, summary_token_threshold=0,
        projection_tiers={0: {}}, tokenizer_model="gpt-4o", history_store=store,
    )


@pytest.mark.asyncio
async def test_live_stream_is_refused():
    history = _history()
    src = PipeElement(name="src")
    src.ports.pipe_output > history.ports.payload_input
    with pytest.raises(UnfinishedPayloadError, match="MessagePayload"):
        await src.async_send_payload(MessagePayload(role="assistant", mode="stream", message_coroutine=_stream()))


@pytest.mark.asyncio
async def test_unrun_tool_call_is_refused():
    history = _history()
    src = PipeElement(name="src")
    src.ports.pipe_output > history.ports.payload_input
    pending = ToolUsePayload()
    pending.model.add_proposed_call(model_tool_name="lookup", tool_call_id="c1")
    with pytest.raises(UnfinishedPayloadError, match="ToolUsePayload"):
        await src.async_send_payload(pending)


@pytest.mark.asyncio
async def test_gateway_emits_the_finished_reply_and_the_ledger_persists_it():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteHistoryStore(db_path=str(Path(tmp) / "h.db"))
        history = _history(store)
        gateway = ChatGatewayElement()
        llm = PipeElement(name="llm")
        gateway.ports.message_output > history.ports.payload_pre_emit_input
        gateway.ports.assistant_message_output > history.ports.payload_input
        llm.ports.pipe_output > gateway.ports.assistant_message_input

        turn = await gateway.submit_message_async("hi")
        await llm.async_send_payload(MessagePayload(role="assistant", mode="stream", message_coroutine=_stream()))
        events = [e async for e in turn.stream()]
        await gateway.ports.output["assistant_message_output"].drain()
        await history.model.flush_store()

        assert [e.type for e in events] == ["token", "token", "done"]
        rows = await store.load_records()
        assert [r.payload_data["role"] for r in rows] == ["user", "assistant"]
        assert rows[1].payload_data["content"] == "Hello world"
        assert rows[1].raw_token_count > 0
