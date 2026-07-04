from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyllments.payloads import ToolUsePayload

DECISION_APPROVED = "approved"
DECISION_DENIED = "denied"


def build_tool_call_view(record: dict[str, Any], index: int) -> dict[str, Any]:
    """Build a serializable view of one tool-call record for application hooks."""
    return {
        "index": index,
        "name": record.get("model_tool_name"),
        "adapter_name": record.get("adapter_name"),
        "provider_name": record.get("provider_name"),
        "tool_name": record.get("tool_name"),
        "description": record.get("description", ""),
        "parameters": record.get("parameters", {}),
        "permission_required": bool(record.get("permission_required")),
        "status": record.get("status"),
        "permission": dict(record.get("permission") or {}),
        "result": record.get("result"),
        "error": record.get("error"),
    }


def build_tool_use_review(payload: ToolUsePayload) -> dict[str, Any]:
    """Build the uniform application gate payload for an arriving ToolUsePayload."""
    return {
        "tools": [
            build_tool_call_view(record, index)
            for index, record in enumerate(payload.model.tool_calls)
        ],
    }


def refresh_tool_use_review(review: dict[str, Any], payload: ToolUsePayload) -> dict[str, Any]:
    """Refresh an existing review dict in place so application references stay valid."""
    review["tools"] = [
        build_tool_call_view(record, index)
        for index, record in enumerate(payload.model.tool_calls)
    ]
    return review


def build_tool_result_notice(payload: ToolUsePayload) -> dict[str, Any]:
    """Build a result notice after execution or denial for application display."""
    return build_tool_use_review(payload)


def pending_permission_indices(payload: ToolUsePayload) -> list[int]:
    """Return list indices for tool calls still awaiting permission."""
    return payload.model.pending_permission_indices()


def normalize_policy_response(
    response: Any,
    pending_indices: list[int],
) -> list[dict[str, Any]] | None:
    """
    Normalize an application policy response into per-tool decisions.

    Returns None when the application only acknowledges and defers decisions.
    """
    if response is None:
        return None
    if isinstance(response, dict):
        decisions = response.get("decisions")
        if decisions is None:
            return None
        if not isinstance(decisions, list):
            raise TypeError("policy response decisions must be a list")
        if len(decisions) != len(pending_indices):
            raise ValueError(
                "policy response decisions must match the number of pending tools"
            )
        return [normalize_decision(item) for item in decisions]
    if isinstance(response, list):
        if len(response) != len(pending_indices):
            raise ValueError(
                "policy response decisions must match the number of pending tools"
            )
        return [normalize_decision(item) for item in response]
    raise TypeError("policy response must be None, a dict with decisions, or a list")


def normalize_decision(item: Any) -> dict[str, Any]:
    """Normalize one decision record to approved/denied with optional reason."""
    if not isinstance(item, dict):
        raise TypeError("each decision must be a dict")
    decision = item.get("decision")
    if decision not in {DECISION_APPROVED, DECISION_DENIED}:
        raise ValueError("decision must be 'approved' or 'denied'")
    normalized = {"decision": decision}
    if item.get("reason") is not None:
        normalized["reason"] = item["reason"]
    if item.get("decided_by") is not None:
        normalized["decided_by"] = item["decided_by"]
    return normalized


def apply_policy_decisions(
    payload: ToolUsePayload,
    pending_indices: list[int],
    decisions: list[dict[str, Any]],
) -> tuple[list[int], list[int]]:
    """
    Apply application decisions to pending tool calls.

    Returns
    -------
    tuple[list[int], list[int]]
        Approved and denied list indices.
    """
    approved: list[int] = []
    denied: list[int] = []
    for index, decision in zip(pending_indices, decisions):
        if decision["decision"] == DECISION_APPROVED:
            payload.model.approve(
                [index],
                decided_by=decision.get("decided_by"),
            )
            approved.append(index)
        else:
            payload.model.deny(
                [index],
                reason=decision.get("reason"),
                decided_by=decision.get("decided_by"),
            )
            denied.append(index)
    return approved, denied


def review_tool_names(review: dict[str, Any]) -> list[str]:
    """Return model tool names from a review notice."""
    return [tool.get("name") for tool in review.get("tools", [])]


def pending_review_tools(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only tools in a review that still await permission."""
    return [
        tool
        for tool in review.get("tools", [])
        if tool.get("permission_required")
        and tool.get("status") == "awaiting_permission"
    ]
