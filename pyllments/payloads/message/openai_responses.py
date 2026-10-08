"""
The OpenAI Responses wire shape of the payloads a model reads.

The request is stateless (``store: false``), so ``input`` is the whole
conversation every time. Messages keep their roles and places; a reply's tool
calls become ``function_call`` items and their results ``function_call_output``
items. A reply that carries OpenAI reasoning is sent back as the output items
OpenAI returned, unchanged; the history decides how long a reply keeps it.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from pyllments.payloads.message.chat_completions import message_entries


def to_responses_input(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    """The ``input`` items of a Responses request."""
    items: list[dict[str, Any]] = []
    for entry, reasoning in message_entries(payloads):
        role = entry["role"]
        text = entry.get("content") or ""
        if role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": entry.get("tool_call_id"),
                "output": text,
            })
        elif role == "assistant":
            if reasoning and reasoning.get("provider") == "openai":
                items.extend(json.loads(json.dumps(reasoning.get("items") or [])))
                continue
            if text:
                items.append({"role": "assistant", "content": text})
            for call in entry.get("tool_calls") or []:
                function = call.get("function") or {}
                arguments = function.get("arguments")
                items.append({
                    "type": "function_call",
                    "call_id": call.get("id"),
                    "name": function.get("name"),
                    "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments or {}),
                })
        else:
            items.append({"role": role, "content": text})
    return items


def to_responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Chat-completions function tools as Responses tool definitions."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        function = tool.get("function") if tool.get("type") == "function" else None
        if function is None:
            converted.append(tool)
            continue
        definition = {
            "type": "function",
            "name": function.get("name"),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        }
        if function.get("description"):
            definition["description"] = function["description"]
        if function.get("strict") is not None:
            definition["strict"] = function["strict"]
        converted.append(definition)
    return converted


def to_responses_tool_choice(choice: Any) -> Any:
    """A chat-completions ``tool_choice`` in the Responses form."""
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "function", "name": (choice.get("function") or {}).get("name")}
    return choice


def to_responses_text_format(response_format: Any) -> dict[str, Any] | None:
    """A chat-completions ``response_format`` as the Responses ``text.format``."""
    if not isinstance(response_format, dict):
        return None
    if response_format.get("type") == "json_schema":
        schema = dict(response_format.get("json_schema") or {})
        return {"type": "json_schema", **schema}
    return {"type": response_format.get("type")}
