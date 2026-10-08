"""
Token usage of one reply, in one shape whatever the provider.

``input_tokens`` counts the whole prompt, cached part included;
``cached_input_tokens`` is the part read from the provider's prompt cache and
``cache_write_tokens`` the part written to it on this request.
"""

from __future__ import annotations

from typing import Any

USAGE_KEYS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")


def _plain(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    dump = getattr(raw, "model_dump", None)
    if callable(dump):
        dumped = dump()
        return dumped if isinstance(dumped, dict) else None
    return None


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def usage_record(input_tokens: Any = 0, cached_input_tokens: Any = 0,
                 cache_write_tokens: Any = 0, output_tokens: Any = 0) -> dict[str, int]:
    return {
        "input_tokens": _int(input_tokens),
        "cached_input_tokens": _int(cached_input_tokens),
        "cache_write_tokens": _int(cache_write_tokens),
        "output_tokens": _int(output_tokens),
    }


def normalize_usage(raw: Any) -> dict[str, int] | None:
    """
    ``raw`` as a usage record, or None when it carries no counts.

    Takes a record already in this shape (what the Anthropic and OpenAI
    backends emit) or chat-completions usage (``prompt_tokens``,
    ``completion_tokens``, ``prompt_tokens_details.cached_tokens``).
    """
    data = _plain(raw)
    if not data:
        return None
    if "cached_input_tokens" in data:
        return usage_record(*(data.get(key) for key in USAGE_KEYS))
    if "prompt_tokens" in data or "completion_tokens" in data:
        details = _plain(data.get("prompt_tokens_details")) or {}
        return usage_record(
            input_tokens=data.get("prompt_tokens"),
            cached_input_tokens=details.get("cached_tokens"),
            cache_write_tokens=details.get("cache_write_tokens"),
            output_tokens=data.get("completion_tokens"),
        )
    return None
