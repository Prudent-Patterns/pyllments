"""
The chat-completions wire shape of the payloads a model reads.

Every backend sends the same ``messages`` list, built here, so an assistant's
tool calls and the tool results that answer them reach the provider in native
form whatever the transport.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from pyllments.payloads.message.message_payload import MessagePayload


def _wire_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = dict(tool_call.get("function") or {})
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        function["arguments"] = json.dumps(arguments if arguments is not None else {})
    return {
        "id": tool_call.get("id"),
        "type": tool_call.get("type") or "function",
        "function": function,
    }


def message_to_chat_completion(message: MessagePayload) -> dict[str, Any]:
    """
    One MessagePayload as a chat-completions message dict.

    An assistant message that called tools carries ``tool_calls`` with the
    arguments as JSON text. A tool message must carry the ``tool_call_id`` it
    answers; a provider rejects one that does not.
    """
    model = message.model
    entry: dict[str, Any] = {"role": model.role, "content": model.content}
    if model.role == "assistant" and model.tool_calls:
        entry["tool_calls"] = [_wire_tool_call(tc) for tc in model.tool_calls]
        if not model.content:
            entry["content"] = None
    if model.role == "tool":
        if not model.tool_call_id:
            raise ValueError(
                "A tool message needs tool_call_id: the id of the assistant tool call it answers."
            )
        entry["tool_call_id"] = model.tool_call_id
        if model.tool_name:
            entry["name"] = model.tool_name
    return entry


def message_entries(payloads: Iterable[Any]) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """
    Message and tool-use payloads, in order, as ``(message, reasoning)`` pairs.

    ``message`` is the chat-completions dict; ``reasoning`` is the reply's
    provider record, for the backend of that provider to send back. A ToolUsePayload
    expands to one tool message per finished record, placed where the payload
    sits, which is right after the assistant message that made the calls when
    the ledger is append-only.
    """
    from pyllments.payloads.tool_use.tool_use_payload import ToolUsePayload

    entries: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for payload in payloads:
        if isinstance(payload, MessagePayload):
            entries.append((message_to_chat_completion(payload), payload.model.reasoning))
        elif isinstance(payload, ToolUsePayload):
            entries.extend((message_to_chat_completion(m), None) for m in payload.to_messages())
        else:
            raise TypeError(
                f"Cannot send a {type(payload).__name__} to a chat model; "
                "convert it to MessagePayload first."
            )
    return entries


def to_chat_completions(payloads: Iterable[Any]) -> list[dict[str, Any]]:
    """Message and tool-use payloads, in order, as the ``messages`` list of a request."""
    return [message for message, _ in message_entries(payloads)]

