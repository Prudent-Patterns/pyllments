"""Tests for HistoryHandler projection tiers and summarization candidates."""

import pytest

from pyllments.elements.history_handler.history_handler_model import HistoryHandlerModel
from pyllments.elements.history_handler.history_projection import (
    ProjectionContext,
    abridge_tool_use,
    default_projection_tiers,
    normalize_projection_tiers,
    stub_tool_use,
)
from pyllments.payloads import MessagePayload, ToolUsePayload
from pyllments.payloads.structured.summary_contract import (
    build_summary_artifact,
    is_summary_request,
)


def _tool_use(content_text: str, ts: float) -> ToolUsePayload:
    payload = ToolUsePayload(timestamp=ts, executor_element_name="main_tools")
    index = payload.model.add_tool_call(
        adapter_name="mcp",
        provider_name="mcp",
        tool_name="search",
        model_tool_name="mcp_search",
        description="search docs",
        parameters={"q": "test"},
    )
    payload.model.attach_result(
        index,
        {"content": [{"type": "text", "text": content_text}], "raw": None, "metadata": {}},
    )
    return payload


def test_default_tiers_include_zero_and_tool_projectors():
    tiers = default_projection_tiers(16000)
    assert 0 in tiers
    assert ToolUsePayload in tiers[0]


def test_normalize_projection_tiers_requires_zero():
    with pytest.raises(ValueError, match="key 0"):
        normalize_projection_tiers({4000: {}}, 16000)


def test_tool_use_abridged_and_stubbed_copies():
    long_text = "x" * 800
    payload = _tool_use(long_text, 1.0)
    pctx = ProjectionContext(
        tier_start=4000,
        tier_end=12000,
        token_distance_from_newest=5000,
        entry_index=1,
        tokenizer_model="gpt-4o",
    )
    abridged = abridge_tool_use(payload, pctx, max_text_chars=100)
    assert abridged is not payload
    assert "[truncated]" in abridged.model.content

    stubbed = stub_tool_use(payload, pctx)
    assert stubbed is not payload
    assert "completed" in stubbed.model.content.lower()


def test_context_projection_uses_tier_by_token_distance():
    model = HistoryHandlerModel(
        context_token_limit=100000,
        history_token_limit=100000,
        summary_token_threshold=100000,
        projection_tiers={
            0: {ToolUsePayload: lambda p, c: p},
            20: {ToolUsePayload: stub_tool_use},
        },
        tokenizer_model="gpt-4o",
    )
    big = _tool_use("y" * 200, 1.0)
    model.load_entries([big])
    model.load_entries(
        [
            MessagePayload(
                role="user",
                content="padding " * 80,
                timestamp=2.0,
            )
        ]
    )

    context = model.get_context_payloads()
    assert len(context) == 2
    assert isinstance(context[0], ToolUsePayload)
    assert isinstance(context[1], MessagePayload)
    assert context[0] is not big
    assert "completed" in context[0].model.content.lower()


def test_summary_request_beyond_threshold():
    model = HistoryHandlerModel(
        context_token_limit=50000,
        history_token_limit=50000,
        summary_token_threshold=10,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    for i in range(5):
        model.load_entries(
            [MessagePayload(role="user", content=f"message {i} " + ("word " * 20), timestamp=float(i))]
        )

    request = model.get_summary_request()
    assert request is not None
    assert is_summary_request(request)
    payloads = request.model.data["source_payloads"]
    entry_ids = request.model.data["source_entry_ids"]
    assert len(payloads) >= 1
    assert len(entry_ids) == len(payloads)
    assert all(isinstance(p, MessagePayload) for p in payloads)

    model.accept_summary_artifact(
        build_summary_artifact(
            content="summary",
            source_entry_ids=entry_ids,
            timestamp=99.0,
        )
    )
    assert model.get_summary_request() is None


def test_summary_payload_marks_only_its_source_entry_ids():
    model = HistoryHandlerModel(
        context_token_limit=50000,
        history_token_limit=50000,
        summary_token_threshold=5,
        projection_tiers={0: {}},
        tokenizer_model="gpt-4o",
    )
    model.load_entries([MessagePayload(role="user", content="a " * 50, timestamp=1.0)])
    model.load_entries([MessagePayload(role="user", content="b " * 50, timestamp=2.0)])
    model.load_entries([MessagePayload(role="user", content="c " * 50, timestamp=3.0)])
    request = model.get_summary_request()
    assert request is not None
    marked_ids = list(request.model.data["source_entry_ids"])
    assert len(marked_ids) >= 2
    model.accept_summary_artifact(
        build_summary_artifact(
            content="done",
            source_entry_ids=marked_ids[:1],
            timestamp=4.0,
        )
    )
    summarized = [e for e in model.history if e.summarized]
    assert len(summarized) == 1
    assert summarized[0].entry_id == marked_ids[0]
    follow_up = model.get_summary_request()
    assert follow_up is not None
    assert marked_ids[0] not in follow_up.model.data["source_entry_ids"]
