"""
Which backend serves a ``provider/model`` name.

One string names both: ``anthropic/claude-haiku-5-5`` goes to Anthropic's API,
``openai/gpt-5.5`` to OpenAI's, ``@cf/meta/llama-3.3-70b-instruct-fp8-fast`` to
Workers AI, and ``cloudflare/openai/gpt-5.5`` to a third-party model through
Cloudflare's AI Gateway.
"""

from __future__ import annotations

# (prefix, backend, whether the backend's model name drops the prefix)
_ROUTES = (
    ("anthropic/", "anthropic", True),
    ("openai/", "openai", True),
    ("cloudflare/", "cloudflare", True),
    ("@cf/", "cloudflare", False),
    ("workers-ai/", "cloudflare", False),
)


def route_model(model_name: str) -> tuple[str, str]:
    """``(backend, model name for that backend)`` for a ``provider/model`` name."""
    for prefix, backend, strip in _ROUTES:
        if model_name.startswith(prefix):
            return backend, model_name[len(prefix):] if strip else model_name
    known = ", ".join(prefix for prefix, _, _ in _ROUTES)
    raise ValueError(f"Model {model_name!r} names no known provider; start it with one of: {known}")
