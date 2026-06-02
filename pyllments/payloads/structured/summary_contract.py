"""StructuredPayload data contracts for history summarization."""

from __future__ import annotations

import time
from typing import Any, List, Optional

from pyllments.payloads.structured.structured_payload import StructuredPayload

SUMMARY_REQUEST_TYPE = "summary_request"
SUMMARY_ARTIFACT_TYPE = "summary"


def build_summary_request(
    source_payloads: List[Any],
    source_entry_ids: List[str],
    instructions: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> StructuredPayload:
    """Build a summarization request emitted by HistoryHandler."""
    return StructuredPayload(
        data={
            "type": SUMMARY_REQUEST_TYPE,
            "source_payloads": source_payloads,
            "source_entry_ids": list(source_entry_ids),
            "instructions": instructions,
            "timestamp": timestamp if timestamp is not None else time.time(),
        }
    )


def build_summary_artifact(
    content: str,
    source_entry_ids: Optional[List[str]] = None,
    strategy: Optional[str] = None,
    model_name: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> StructuredPayload:
    """Build a summary artifact returned to HistoryHandler.summary_input."""
    return StructuredPayload(
        data={
            "type": SUMMARY_ARTIFACT_TYPE,
            "content": content or "",
            "source_entry_ids": list(source_entry_ids or []),
            "strategy": strategy,
            "model_name": model_name,
            "timestamp": timestamp if timestamp is not None else time.time(),
        }
    )


def is_summary_request(payload: Any) -> bool:
    data = getattr(getattr(payload, "model", None), "data", None)
    return isinstance(data, dict) and data.get("type") == SUMMARY_REQUEST_TYPE


def is_summary_artifact(payload: Any) -> bool:
    data = getattr(getattr(payload, "model", None), "data", None)
    return isinstance(data, dict) and data.get("type") == SUMMARY_ARTIFACT_TYPE


def summary_artifact_entry_ids(payload: Any) -> List[str]:
    if not is_summary_artifact(payload):
        return []
    data = payload.model.data or {}
    return list(data.get("source_entry_ids") or [])


def summary_artifact_content(payload: Any) -> str:
    if not is_summary_artifact(payload):
        return ""
    return str((payload.model.data or {}).get("content") or "")


def summary_request_fields(payload: Any) -> tuple[List[Any], List[str], Optional[str]]:
    if not is_summary_request(payload):
        return [], [], None
    data = payload.model.data or {}
    return (
        list(data.get("source_payloads") or []),
        list(data.get("source_entry_ids") or []),
        data.get("instructions"),
    )
