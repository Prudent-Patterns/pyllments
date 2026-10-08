"""
Whether each request only appended to the one before it.

Every provider's prompt cache, and Anthropic's check on returned thinking,
compare a request with the previous one from the start. A change inside a turn
is a bug that silently costs money; at a turn's start, the history dropping the
last turn's notices and reasoning is expected.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from pyllments.payloads.message.chat_completions import message_entries


def _digest(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class RequestTracker:
    """Remembers the last request's messages and settings to compare the next one with."""

    def __init__(self):
        self._messages: list[str] | None = None
        self._settings: str | None = None
        self._user_messages = 0

    def check(self, payloads: Iterable[Any], settings: dict[str, Any]) -> dict[str, Any]:
        """The report for this request, then remember it as the last one."""
        entries = message_entries(payloads)
        messages = [_digest(entry) for entry in entries]
        user_messages = sum(1 for message, _ in entries if message["role"] == "user")
        settings_digest = _digest(settings)
        if self._messages is None:
            report = {"first_request": True, "appended": True, "changed_at": None,
                      "same_turn": False, "settings_changed": False}
        else:
            previous = self._messages
            changed_at = next(
                (index for index, (old, new) in enumerate(zip(previous, messages)) if old != new),
                None,
            )
            if changed_at is None and len(messages) < len(previous):
                changed_at = len(messages)
            report = {
                "first_request": False,
                "appended": changed_at is None,
                "changed_at": changed_at,
                "same_turn": user_messages == self._user_messages,
                "settings_changed": settings_digest != self._settings,
            }
        self._messages, self._settings, self._user_messages = messages, settings_digest, user_messages
        return report
