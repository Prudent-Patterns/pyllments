"""Tests for SummarizerElement with a stubbed LLM backend."""

from unittest.mock import MagicMock

import pytest

from pyllments.elements.summarizer import SummarizerElement
from pyllments.elements.summarizer.summarizer_model import SummarizerModel
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.payloads.structured.summary_contract import (
    build_summary_request,
    is_summary_artifact,
)


@pytest.mark.asyncio
async def test_summarizer_emits_structured_summary(monkeypatch):
    emitted = []

    async def fake_stage_emit(self, **kwargs):
        emitted.append(kwargs.get("context"))

    summarizer = SummarizerElement(
        backend="openrouter",
        model_name="openai/gpt-4o-mini",
        api_key="test-key",
    )
    response_payload = MessagePayload(
        role="assistant",
        content="Short summary.",
        mode="atomic",
    )
    summarizer.chat_model.generate_response = MagicMock(return_value=response_payload)
    monkeypatch.setattr(
        type(summarizer.ports.output["summary_output"]),
        "stage_emit",
        fake_stage_emit,
    )

    request = build_summary_request(
        source_payloads=[MessagePayload(role="user", content="Long chat " * 30)],
        source_entry_ids=["entry-a", "entry-b"],
    )
    await summarizer._summarize_and_emit(
        summarizer.model.build_messages_from_request(request),
        list(request.model.data["source_entry_ids"]),
    )

    assert len(emitted) == 1
    summary = emitted[0]
    assert isinstance(summary, StructuredPayload)
    assert is_summary_artifact(summary)
    assert summary.model.data["content"] == "Short summary."
    assert summary.model.data["source_entry_ids"] == ["entry-a", "entry-b"]


def test_summarizer_model_builds_system_and_user_messages():
    model = SummarizerModel()
    messages = model.build_messages_from_sources(
        [MessagePayload(role="user", content="hello")]
    )
    assert messages[0].model.role == "system"
    assert messages[-1].model.role == "user"
    assert any(m.model.content == "hello" for m in messages)
