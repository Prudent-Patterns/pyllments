"""Tests for structured summary request/artifact contracts."""

import asyncio
import tempfile
from pathlib import Path

from pyllments.elements.context_builder.context_builder_element import ContextBuilderElement
from pyllments.elements.history_handler.history_handler_model import HistoryHandlerModel
from pyllments.elements.history_handler.history_store import (
    SQLiteHistoryStore,
    new_entry_id,
    payload_to_record,
    record_to_payload,
)
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.payloads.structured.summary_contract import (
    SUMMARY_ARTIFACT_TYPE,
    SUMMARY_REQUEST_TYPE,
    build_summary_artifact,
    build_summary_request,
    is_summary_artifact,
    is_summary_request,
)


def test_summary_request_contract():
    msg = MessagePayload(role="user", content="hello")
    request = build_summary_request(
        source_payloads=[msg],
        source_entry_ids=["id-1"],
        instructions="Be brief.",
    )
    assert is_summary_request(request)
    assert request.model.data["type"] == SUMMARY_REQUEST_TYPE
    assert request.model.data["source_payloads"][0] is msg
    assert request.model.data["source_entry_ids"] == ["id-1"]


def test_context_builder_converts_summary_structured_payload():
    cb = ContextBuilderElement(input_map={}, emit_order=[])
    summary = build_summary_artifact(
        content="User asked about weather.",
        source_entry_ids=["a"],
    )
    result = cb._convert_payload_to_message("history", summary)
    assert result.model.role == "system"
    assert "Conversation summary" in result.model.content
    assert "weather" in result.model.content


def test_structured_summary_sqlite_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        async def _run():
            db_path = str(Path(tmp) / "summary.db")
            store = SQLiteHistoryStore(db_path=db_path)
            summary = build_summary_artifact(
                content="condensed history",
                source_entry_ids=["e1", "e2"],
                strategy="default",
                model_name="openai/gpt-4o-mini",
                timestamp=42.0,
            )
            record = payload_to_record(new_entry_id(), summary, 12)
            assert record is not None
            await store.append_records([record])
            loaded = (await store.load_records())[0]
            restored = record_to_payload(loaded)
            assert isinstance(restored, StructuredPayload)
            assert is_summary_artifact(restored)
            assert restored.model.data["content"] == "condensed history"
            assert restored.model.data["source_entry_ids"] == ["e1", "e2"]

        asyncio.run(_run())


def test_non_summary_structured_does_not_mark_history():
    model = HistoryHandlerModel(
        context_token_limit=50000,
        history_token_limit=50000,
        summary_token_threshold=5,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    model.load_entries([MessagePayload(role="user", content="a " * 50, timestamp=1.0)])
    model.get_summary_request()
    model.accept_summary_artifact(StructuredPayload(data={"type": "other", "value": 1}))
    assert not any(entry.summarized for entry in model.history)
