"""
The model-facing form of a ToolUsePayload: one tool message per finished record.
"""

from __future__ import annotations

from typing import Any

from pyllments.payloads.message.message_payload import MessagePayload
from pyllments.payloads.tool_use.tool_use_model import TERMINAL_STATUSES


def tool_result_text(record: dict[str, Any]) -> str:
    """What the model reads for one finished record: its result, or why there is none."""
    status = record.get("status")
    if status in {"succeeded", "orphaned_completed"}:
        result = record.get("result") or {}
        return "\n".join(
            str(item.get("text", ""))
            for item in result.get("content") or []
            if item.get("type", "text") == "text"
        )
    if status == "failed":
        error = record.get("error") or {}
        text = f"Error: {error.get('message') or 'tool failed'}"
        if error.get("retryable"):
            text += " (retryable)"
        return text
    if status == "denied":
        reason = (record.get("permission") or {}).get("reason")
        return f"Denied: {reason}" if reason else "Denied"
    if status == "cancelled":
        error = record.get("error") or {}
        return f"Cancelled: {error.get('message') or 'tool invocation was cancelled'}"
    return ""


def finished_records(payload) -> list[dict[str, Any]]:
    return [
        record for record in payload.model.tool_calls if record.get("status") in TERMINAL_STATUSES
    ]


def tool_result_messages(payload) -> list[MessagePayload]:
    """
    Finished records with a provider ``tool_call_id`` as ``role: tool`` messages.

    A record without an id has no assistant tool call to answer and is left out;
    :meth:`ToolUsePayload.to_messages` decides what to do with those.
    """
    messages: list[MessagePayload] = []
    for record in finished_records(payload):
        call_id = record.get("tool_call_id")
        if not call_id:
            continue
        messages.append(
            MessagePayload(
                role="tool",
                content=tool_result_text(record),
                tool_call_id=call_id,
                tool_name=record.get("model_tool_name") or record.get("tool_name") or None,
                timestamp=record.get("updated_at") or payload.model.timestamp,
            )
        )
    return messages
