"""
The Anthropic Messages wire shape of the payloads a model reads.

Built on the chat-completions form so every backend reads a payload the same
way, then reshaped: the leading system messages become ``system``, a later one
stays where it was as a mid-conversation system message, tool calls become
``tool_use`` blocks and their results ``tool_result`` blocks in one user turn.
A reply that carries Anthropic reasoning is sent back as the blocks Anthropic
returned, unchanged; the history decides how long a reply keeps it.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from pyllments.payloads.message.chat_completions import message_entries

_SYSTEM_ROLES = ("system", "developer")


def _tool_input(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    try:
        parsed = json.loads(arguments) if arguments else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assistant_blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if entry.get("content"):
        blocks.append({"type": "text", "text": entry["content"]})
    for call in entry.get("tool_calls") or []:
        function = call.get("function") or {}
        blocks.append({
            "type": "tool_use",
            "id": call.get("id"),
            "name": function.get("name"),
            "input": _tool_input(function.get("arguments")),
        })
    return blocks


def _user_turn(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "user", "content": blocks}


def to_anthropic_messages(payloads: Iterable[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    ``(system, messages)`` for a Messages request.

    Consecutive user-side entries (tool results, then any text) share one user
    turn, results first, as Anthropic requires. A system message after the
    first conversational one stays in place when it follows a user turn and is
    last or followed by an assistant turn; anywhere else it is sent as user
    text, the only place Anthropic accepts it.
    """
    entries = message_entries(payloads)
    roles = [entry["role"] for entry, _ in entries]

    system: list[dict[str, Any]] = []
    index = 0
    while index < len(entries) and roles[index] in _SYSTEM_ROLES:
        text = entries[index][0].get("content") or ""
        if text:
            system.append({"type": "text", "text": text})
        index += 1

    messages: list[dict[str, Any]] = []

    def add_user_blocks(blocks: list[dict[str, Any]]) -> None:
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"].extend(blocks)
        else:
            messages.append(_user_turn(blocks))

    for position in range(index, len(entries)):
        entry, reasoning = entries[position]
        role = entry["role"]
        text = entry.get("content") or ""
        if role in _SYSTEM_ROLES:
            follows_user = bool(messages) and messages[-1]["role"] == "user"
            next_role = roles[position + 1] if position + 1 < len(roles) else None
            if follows_user and next_role in (None, "assistant"):
                messages.append({"role": "system", "content": text})
            elif text:
                add_user_blocks([{"type": "text", "text": text}])
        elif role == "user":
            if text:
                add_user_blocks([{"type": "text", "text": text}])
        elif role == "tool":
            add_user_blocks([{
                "type": "tool_result",
                "tool_use_id": entry.get("tool_call_id"),
                "content": text,
            }])
        elif role == "assistant":
            if reasoning and reasoning.get("provider") == "anthropic":
                blocks = json.loads(json.dumps(reasoning.get("content") or []))
            else:
                blocks = _assistant_blocks(entry)
            if blocks:
                messages.append({"role": "assistant", "content": blocks})
        else:
            raise ValueError(f"Anthropic has no message role {role!r}")
    return system, messages


def to_anthropic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Chat-completions function tools as Anthropic tool definitions."""
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        function = tool.get("function") if tool.get("type") == "function" else None
        if function is None:
            converted.append(tool)
            continue
        definition = {
            "name": function.get("name"),
            "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
        }
        if function.get("description"):
            definition["description"] = function["description"]
        if function.get("strict") is not None:
            definition["strict"] = function["strict"]
        converted.append(definition)
    return converted


def to_anthropic_tool_choice(choice: Any) -> dict[str, Any]:
    """A chat-completions ``tool_choice`` in Anthropic's form."""
    if isinstance(choice, dict):
        if choice.get("type") == "function":
            return {"type": "tool", "name": (choice.get("function") or {}).get("name")}
        return choice
    return {"none": {"type": "none"}, "required": {"type": "any"}}.get(choice, {"type": "auto"})
