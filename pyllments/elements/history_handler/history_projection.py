"""
Token-tiered payload projection for HistoryHandler.

History stores raw payloads; context emission applies numeric tier boundaries and
per-payload-type projector callables without mutating stored originals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from pyllments.common.tokenizers import get_token_len
from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload
from pyllments.payloads.structured.summary_contract import (
    SUMMARY_ARTIFACT_TYPE,
    summary_artifact_content,
)

# Payload -> projected payload
Projector = Callable[[Any, "ProjectionContext"], Any]

# Tier boundary -> {payload_type: projector}
TierProjectors = Dict[Type, Projector]
ProjectionTiers = Dict[int, TierProjectors]


@dataclass
class HistoryEntry:
    """Internal ledger record; not a public framework payload."""

    payload: Any
    raw_token_count: int
    timestamp: float
    entry_id: str = ""
    summarized: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class ProjectionContext:
    """Context passed to tier projectors when building context output."""

    tier_start: int
    tier_end: Optional[int]
    token_distance_from_newest: int
    entry_index: int
    tokenizer_model: str
    remaining_context_budget: Optional[int] = None


@dataclass
class TierInterval:
    """Normalized numeric tier: [start, end) token distance from newest history edge."""

    start: int
    end: Optional[int]
    projectors: TierProjectors = field(default_factory=dict)


def normalize_projection_tiers(
    projection_tiers: Optional[ProjectionTiers],
    context_token_limit: int,
) -> List[TierInterval]:
    """
    Validate and normalize a numeric tier dictionary into sorted intervals.

    Keys are token-distance lower bounds from the newest edge; the first key must be 0.
    """
    if not projection_tiers:
        projection_tiers = default_projection_tiers(context_token_limit)

    if 0 not in projection_tiers:
        raise ValueError("projection_tiers must include key 0 (newest tier).")

    starts = sorted(projection_tiers.keys())
    if any(k < 0 for k in starts):
        raise ValueError("projection_tiers keys must be non-negative integers.")

    intervals: List[TierInterval] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else None
        projectors = projection_tiers.get(start) or {}
        intervals.append(TierInterval(start=start, end=end, projectors=projectors))
    return intervals


def default_projection_tiers(context_token_limit: int) -> ProjectionTiers:
    """Well-chosen defaults: tool responses degrade by age; messages stay unchanged."""
    mid = max(1, int(context_token_limit * 0.50))
    far = max(mid + 1, int(context_token_limit * 0.80))
    return {
        0: {ToolUsePayload: keep_full},
        mid: {ToolUsePayload: abridge_tool_use},
        far: {ToolUsePayload: stub_tool_use},
    }


def resolve_tier_interval(
    token_distance_from_newest: int,
    intervals: List[TierInterval],
) -> TierInterval:
    """Return the tier interval for a given distance from the newest history edge."""
    chosen = intervals[0]
    for interval in intervals:
        if token_distance_from_newest >= interval.start:
            chosen = interval
        else:
            break
    return chosen


def project_payload(
    payload: Any,
    interval: TierInterval,
    context: ProjectionContext,
) -> Any:
    """Apply the projector for this payload type, or identity if none registered."""
    projector = interval.projectors.get(type(payload))
    if projector is None:
        return payload
    return projector(payload, context)


def payload_token_count(payload: Any, tokenizer_model: str) -> int:
    """Estimate tokens for a payload's string content."""
    if isinstance(payload, MessagePayload):
        return get_token_len(payload.model.content or "", tokenizer_model)
    if isinstance(payload, ToolUsePayload):
        if not payload.model.tool_uses:
            return 0
        return get_token_len(payload.model.content or "", tokenizer_model)
    if isinstance(payload, StructuredPayload):
        data = payload.model.data or {}
        if data.get("type") == SUMMARY_ARTIFACT_TYPE:
            return get_token_len(summary_artifact_content(payload), tokenizer_model)
        return get_token_len(str(data), tokenizer_model)
    content = getattr(getattr(payload, "model", None), "content", None)
    if isinstance(content, str):
        return get_token_len(content, tokenizer_model)
    return get_token_len(str(payload), tokenizer_model)


def keep_full(payload: Any, context: ProjectionContext) -> Any:
    return payload


def abridge_tool_use(
    payload: ToolUsePayload,
    context: ProjectionContext,
    max_text_chars: int = 500,
) -> ToolUsePayload:
    """Return a copy with truncated tool result text."""
    new_tool_uses: Dict[str, Any] = {}
    for tool_use_id, record in payload.model.tool_uses.items():
        new_record = dict(record)
        result = new_record.get("result")
        if result and result.get("content"):
            new_content = []
            for item in result["content"]:
                text = item.get("text", "")
                if len(text) > max_text_chars:
                    text = text[:max_text_chars] + "... [truncated]"
                new_content.append({**item, "text": text})
            new_record["result"] = {**result, "content": new_content}
        new_tool_uses[tool_use_id] = new_record
    return ToolUsePayload(
        tool_uses=new_tool_uses,
        timestamp=payload.model.timestamp,
        payload_id=payload.model.payload_id,
        turn_id=payload.model.turn_id,
        status=payload.model.status,
    )


def stub_tool_use(
    payload: ToolUsePayload,
    context: ProjectionContext,
) -> ToolUsePayload:
    """Return a minimal copy preserving tool identity and high-level outcome."""
    stub_uses: Dict[str, Any] = {}
    for tool_use_id, record in payload.model.tool_uses.items():
        tool_name = record.get("model_tool_name", tool_use_id)
        status = record.get("status", "completed")
        outcome = status if status in {"failed", "denied"} else "completed"
        stub_uses[tool_use_id] = {
            **record,
            "parameters": None,
            "result": {
                "content": [
                    {"type": "text", "text": f"Tool {tool_name} {outcome}."}
                ],
                "raw": None,
                "metadata": {},
            },
        }
    return ToolUsePayload(
        tool_uses=stub_uses,
        timestamp=payload.model.timestamp,
        payload_id=payload.model.payload_id,
        turn_id=payload.model.turn_id,
        status=payload.model.status,
    )
