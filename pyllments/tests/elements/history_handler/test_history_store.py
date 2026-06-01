"""Tests for HistoryStore persistence."""

import asyncio
import tempfile
from pathlib import Path

from pyllments.elements.history_handler.history_handler_model import HistoryHandlerModel
from pyllments.elements.history_handler.history_store import (
    SQLiteHistoryStore,
    payload_to_record,
    record_to_payload,
    new_entry_id,
)
from pyllments.payloads import MessagePayload, ToolsResponsePayload


def test_sqlite_roundtrip_message_and_tool():
    with tempfile.TemporaryDirectory() as tmp:
        async def _run():
            db_path = str(Path(tmp) / "test.db")
            store = SQLiteHistoryStore(db_path=db_path)

            msg = MessagePayload(role="user", content="hello", timestamp=1.0)
            tool = ToolsResponsePayload(
                tool_responses={
                    "t": {
                        "mcp_name": "m",
                        "tool_name": "fn",
                        "response": {"content": [{"type": "text", "text": "ok"}]},
                    }
                },
                timestamp=2.0,
            )
            records = [
                payload_to_record(new_entry_id(), msg, 5),
                payload_to_record(new_entry_id(), tool, 10),
            ]
            records = [r for r in records if r is not None]
            await store.append_records(records)

            loaded = await store.load_records()
            assert len(loaded) == 2
            payloads = [record_to_payload(r) for r in loaded]
            assert isinstance(payloads[0], MessagePayload)
            assert payloads[0].model.content == "hello"
            assert isinstance(payloads[1], ToolsResponsePayload)

        asyncio.run(_run())


def test_model_persist_reload():
    with tempfile.TemporaryDirectory() as tmp:
        async def _run():
            db_path = str(Path(tmp) / "hist.db")
            model = HistoryHandlerModel(
                persist=True,
                db_path=db_path,
                history_token_limit=10000,
                context_token_limit=10000,
                tokenizer_model="gpt-4o",
            )
            await model.await_store_ready()
            model.load_entries([MessagePayload(role="user", content="persisted", timestamp=1.0)])
            await model.flush_store()

            model2 = HistoryHandlerModel(
                persist=True,
                db_path=db_path,
                history_token_limit=10000,
                context_token_limit=10000,
                tokenizer_model="gpt-4o",
            )
            await model2.await_store_ready()
            assert len(model2.history) == 1
            assert model2.history[0].payload.model.content == "persisted"

        asyncio.run(_run())


def test_eviction_deletes_from_store():
    with tempfile.TemporaryDirectory() as tmp:
        async def _run():
            db_path = str(Path(tmp) / "evict.db")
            store = SQLiteHistoryStore(db_path=db_path)
            model = HistoryHandlerModel(
                persist=True,
                history_store=store,
                history_token_limit=10000,
                context_token_limit=10000,
                tokenizer_model="gpt-4o",
            )
            await model.await_store_ready()
            model.load_entries(
                [MessagePayload(role="user", content="alpha " * 20, timestamp=1.0)]
            )
            model.history_token_limit = model.history[0].raw_token_count + 1
            model.load_entries(
                [
                    MessagePayload(
                        role="user",
                        content="beta beta",
                        timestamp=2.0,
                    )
                ]
            )
            await model.flush_store()

            remaining = await store.load_records()
            assert len(remaining) == 1
            assert remaining[0].timestamp == 2.0

        asyncio.run(_run())


def test_mark_summarized_on_store():
    with tempfile.TemporaryDirectory() as tmp:
        async def _run():
            db_path = str(Path(tmp) / "sum.db")
            store = SQLiteHistoryStore(db_path=db_path)
            entry_id = new_entry_id()
            record = payload_to_record(
                entry_id,
                MessagePayload(role="user", content="old", timestamp=1.0),
                10,
            )
            await store.append_records([record])
            await store.mark_summarized([entry_id])
            loaded = (await store.load_records())[0]
            assert loaded.summarized is True

        asyncio.run(_run())


def test_accept_summary_marks_candidate_entry_ids():
    model = HistoryHandlerModel(
        context_token_limit=50000,
        history_token_limit=50000,
        summary_token_threshold=5,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    model.load_entries([MessagePayload(role="user", content="a " * 50, timestamp=1.0)])
    model.load_entries([MessagePayload(role="user", content="b " * 50, timestamp=2.0)])
    assert model.get_summary_candidate_payloads()
    candidate_ids = list(model._last_summary_candidate_entry_ids)
    model.accept_summary_artifact(
        MessagePayload(role="system", content="summary", timestamp=3.0)
    )
    assert model.get_summary_candidate_payloads() == []
    for entry in model.history:
        if entry.entry_id in candidate_ids:
            assert entry.summarized
