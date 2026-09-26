"""Turn a finished assistant message's provider tool calls into a proposed ToolUsePayload.

The LLM element always emits a MessagePayload. This helper is the explicit
tool port: one payload, proposed records, provider call ids kept.
"""

from __future__ import annotations

import json
from typing import Any

from pyllments.payloads.message import MessagePayload
from pyllments.payloads.tool_use import ToolUsePayload


def parse_tool_arguments(arguments: str | dict | None) -> dict:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    text = arguments.strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("tool_arguments_not_object")
    return parsed


def proposed_tool_use_from_message(message: MessagePayload) -> ToolUsePayload | None:
    """Build a proposed ToolUsePayload, or None when the message has no tool calls."""
    raw_calls = list(message.model.tool_calls or [])
    if not raw_calls:
        return None
    payload = ToolUsePayload()
    for tool_call in raw_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") or {}
        name = str(function.get("name") or "")
        payload.model.add_proposed_call(
            model_tool_name=name,
            parameters=parse_tool_arguments(function.get("arguments")),
            tool_call_id=tool_call.get("id"),
        )
    if not payload.model.tool_calls:
        return None
    return payload


def tool_call_parameters(record: dict[str, Any]) -> dict:
    parameters = record.get("parameters") or {}
    return parameters if isinstance(parameters, dict) else {}
