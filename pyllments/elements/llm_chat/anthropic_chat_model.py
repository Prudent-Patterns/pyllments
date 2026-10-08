import json
import os
import re
from typing import Any

import param
from dotenv import load_dotenv
from loguru import logger

from pyllments.elements.llm_chat.http_chat_model import HttpChatModel, wrap_json
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.message.anthropic_messages import (
    to_anthropic_messages,
    to_anthropic_tool_choice,
    to_anthropic_tools,
)
from pyllments.payloads.message.usage import usage_record

ANTHROPIC_VERSION = "2023-06-01"
THINKING_BINDING_BETA = "thinking-binding-controls-2026-08-01"
_THINKING_TYPES = ("thinking", "redacted_thinking")


# Families whose models from this version on reject a forced tool call
# (tool_choice any / tool) with a 400.
_NO_FORCED_TOOL_CHOICE_FROM = {"opus": (5, 5), "sonnet": (5, 5), "fable": (5, 1), "mythos": (5, 1)}
_ADAPTIVE_THINKING_FROM = (4, 6)


def _family_version(model_name: str) -> tuple[str, tuple[int, int]] | None:
    """``("sonnet", (5, 5))`` for ``claude-sonnet-5-5``; None for names it cannot read."""
    match = re.match(r"^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-|$)", model_name)
    if match is None:
        return None
    return match.group(1), (int(match.group(2)), int(match.group(3) or 0))


def _profile(model_name: str) -> dict[str, bool]:
    """What this model accepts, where Claude models differ."""
    parsed = _family_version(model_name)
    if parsed is None:
        return {"adaptive_thinking": False, "forced_tool_choice": True}
    family, version = parsed
    no_forced_from = _NO_FORCED_TOOL_CHOICE_FROM.get(family)
    return {
        "adaptive_thinking": version >= _ADAPTIVE_THINKING_FROM,
        "forced_tool_choice": no_forced_from is None or version < no_forced_from,
    }


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    """Anthropic usage as a usage record; its input_tokens excludes the cached part."""
    read = raw.get("cache_read_input_tokens") or 0
    written = raw.get("cache_creation_input_tokens") or 0
    return usage_record(
        input_tokens=(raw.get("input_tokens") or 0) + read + written,
        cached_input_tokens=read,
        cache_write_tokens=written,
        output_tokens=raw.get("output_tokens"),
    )


def _reasoning(content: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The reply's blocks to send back, when it thought; None when it did not."""
    if any(block.get("type") in _THINKING_TYPES for block in content):
        return {"provider": "anthropic", "content": content}
    return None


def _refusal_error(stop_details: Any) -> ValueError:
    category = stop_details.get("category") if isinstance(stop_details, dict) else None
    return ValueError(f"Anthropic declined the request (refusal, category {category})")


def _report_transformations(transformations: list[dict[str, Any]]) -> None:
    """Say so when Anthropic dropped thinking we sent back: the history before it changed."""
    dropped = [item for item in transformations if item.get("type") == "thinking_dropped"]
    if dropped:
        logger.warning(
            "Anthropic dropped {} sent-back thinking block(s): {}",
            len(dropped),
            ", ".join(f"{item.get('path')} ({item.get('reason')})" for item in dropped),
        )


def _completion(response: dict[str, Any]) -> dict[str, Any]:
    """A non-streamed Messages response in the chat-completions shape MessageModel reads."""
    _report_transformations(response.get("input_transformations") or [])
    if response.get("stop_reason") == "refusal":
        raise _refusal_error(response.get("stop_details"))
    content = response.get("content") or []
    text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    tool_calls = [
        {
            "id": block.get("id"),
            "type": "function",
            "function": {"name": block.get("name"), "arguments": json.dumps(block.get("input") or {})},
        }
        for block in content
        if block.get("type") == "tool_use"
    ]
    return {
        "choices": [{"message": {"role": "assistant", "content": text, "tool_calls": tool_calls}}],
        "usage": _usage(response.get("usage") or {}),
        "reasoning": _reasoning(content),
    }


class _StreamDecoder:
    """Anthropic stream events as chat-completions chunks, assembling the reply's blocks."""

    def __init__(self):
        self.blocks: dict[int, dict[str, Any]] = {}
        self.json_parts: dict[int, list[str]] = {}
        self.tool_index: dict[int, int] = {}
        self.usage: dict[str, Any] = {}
        self.stop_reason: str | None = None
        self.stop_details: Any = None
        self.transformations: list[dict[str, Any]] = []

    @staticmethod
    def _chunk(delta: dict[str, Any]) -> dict[str, Any]:
        return {"choices": [{"delta": delta}]}

    def _tool_delta(self, index: int, **fields) -> dict[str, Any]:
        return self._chunk({"tool_calls": [{"index": self.tool_index[index], **fields}]})

    def decode(self, event: dict[str, Any]) -> dict[str, Any] | None:
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message") or {}
            self.usage.update(message.get("usage") or {})
            self.transformations = message.get("input_transformations") or []
        elif kind == "content_block_start":
            index = event.get("index", len(self.blocks))
            block = dict(event.get("content_block") or {})
            self.blocks[index] = block
            if block.get("type") == "tool_use":
                self.tool_index[index] = len(self.tool_index)
                self.json_parts[index] = []
                return self._tool_delta(
                    index,
                    id=block.get("id"),
                    type="function",
                    function={"name": block.get("name"), "arguments": ""},
                )
            if block.get("type") == "text" and block.get("text"):
                return self._chunk({"content": block["text"]})
        elif kind == "content_block_delta":
            index = event.get("index")
            block = self.blocks.get(index)
            delta = event.get("delta") or {}
            step = delta.get("type")
            if block is None:
                return None
            if step == "text_delta":
                block["text"] = block.get("text", "") + delta.get("text", "")
                return self._chunk({"content": delta.get("text", "")})
            if step == "input_json_delta":
                part = delta.get("partial_json", "")
                self.json_parts[index].append(part)
                return self._tool_delta(index, function={"arguments": part}) if part else None
            if step == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")
            elif step == "signature_delta":
                block["signature"] = block.get("signature", "") + delta.get("signature", "")
        elif kind == "content_block_stop":
            index = event.get("index")
            block = self.blocks.get(index)
            if block is not None and block.get("type") == "tool_use":
                arguments = "".join(self.json_parts.get(index) or [])
                if arguments:
                    try:
                        block["input"] = json.loads(arguments)
                    except ValueError:
                        # Cut off mid-call (max_tokens): the call is unusable either way.
                        block["input"] = {}
                elif block.get("input"):
                    # The whole input came with the start event; pass it on as one delta.
                    return self._tool_delta(index, function={"arguments": json.dumps(block["input"])})
                else:
                    block["input"] = {}
        elif kind == "message_delta":
            delta = event.get("delta") or {}
            self.stop_reason = delta.get("stop_reason") or self.stop_reason
            self.stop_details = delta.get("stop_details") or self.stop_details
            self.usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
        elif kind == "error":
            raise ValueError(f"Anthropic stream error: {event.get('error')}")
        return None

    def closing_chunk(self) -> dict[str, Any]:
        if self.stop_reason == "refusal":
            raise _refusal_error(self.stop_details)
        content = [self.blocks[index] for index in sorted(self.blocks)]
        return {
            "choices": [],
            "usage": _usage(self.usage),
            "reasoning": _reasoning(content),
        }


class AnthropicChatModel(HttpChatModel):
    """
    Chat model that calls Anthropic's Messages API directly.

    Caching takes two of Anthropic's four breakpoints: one fixed after the leading
    system messages, and the top-level automatic one that Anthropic moves to the
    last cacheable block as the conversation grows. Thinking is
    adaptive; a reply that thought keeps Anthropic's blocks in its ``reasoning``,
    and is sent back with them (the history keeps them for the turn). If the
    history before a sent-back block changed, ``prefix_mismatch_behavior``
    "drop_block" has Anthropic drop that reasoning instead of failing the request.
    """

    model_name = param.String(default="claude-haiku-5-5", doc="Anthropic model id")
    model_args = param.Dict(
        default={},
        doc=(
            "Extra request fields, e.g. ``output_config``. A chat-completions "
            "``tool_choice`` or ``max_tokens`` is translated."
        ),
    )
    output_mode = param.Selector(
        objects=["atomic", "stream"],
        default="stream",
        doc="Whether to stream the response or return it all at once",
    )
    tools = param.List(default=None, doc="Chat-completions function tools; sent in Anthropic's form")
    api_key = param.String(
        default=None,
        allow_None=True,
        doc="Anthropic API key. Falls back to ANTHROPIC_API_KEY when not provided.",
    )
    base_url = param.String(default="https://api.anthropic.com", doc="API root, without /v1")
    max_tokens = param.Integer(
        default=16000,
        bounds=(1, None),
        doc="Cap on the reply, thinking included",
    )
    thinking = param.Dict(
        default={"type": "adaptive"},
        allow_None=True,
        doc=(
            "The ``thinking`` request field; None leaves it out. Adaptive thinking is "
            "left out on its own for models before Claude 4.6, which do not have it."
        ),
    )
    prefix_mismatch_behavior = param.Selector(
        objects=["drop_block", "error", None],
        default="drop_block",
        doc=(
            "What Anthropic does with sent-back thinking whose earlier history changed: "
            "drop it and answer, or fail the request. None sends no setting."
        ),
    )
    cache = param.Selector(
        objects=["auto", "off"],
        default="auto",
        doc=(
            "'auto': Anthropic's automatic caching plus a fixed breakpoint after the "
            "leading system messages. 'off': no cache markers."
        ),
    )
    cache_ttl = param.Selector(objects=["5m", "1h"], default="5m", doc="How long a cache entry lives")
    headers = param.Dict(default={}, doc="Extra request headers")

    error_label = "Anthropic request failed"

    def _request_target(self, betas: list[str]) -> tuple[str, dict[str, str]]:
        load_dotenv(override=False)
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY in the environment or "
                ".env, or pass api_key to LLMChatElement."
            )
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)
        headers.update({str(key): str(value) for key, value in self.headers.items()})
        return f"{self.base_url.rstrip('/')}/v1/messages", headers

    def _request(self, messages: list[MessagePayload], stream: bool) -> tuple[str, dict[str, str], dict[str, Any]]:
        system, wire_messages = to_anthropic_messages(messages)
        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": wire_messages,
            "stream": stream,
        }
        cache_control = None
        if self.cache == "auto":
            cache_control = {"type": "ephemeral"}
            if self.cache_ttl == "1h":
                cache_control["ttl"] = "1h"
        if system:
            if cache_control:
                # A fixed read point after the system prompt: still a hit when the
                # history window has been trimmed.
                system[-1]["cache_control"] = dict(cache_control)
            body["system"] = system
        if self.tools:
            body["tools"] = to_anthropic_tools(self.tools)
        betas: list[str] = []
        profile = _profile(self.model_name)
        adaptive = (self.thinking or {}).get("type") == "adaptive"
        if self.thinking is not None and (profile["adaptive_thinking"] or not adaptive):
            thinking = dict(self.thinking)
            if thinking.get("type") == "adaptive" and self.prefix_mismatch_behavior:
                thinking["block_binding"] = {"prefix_mismatch_behavior": self.prefix_mismatch_behavior}
                betas.append(THINKING_BINDING_BETA)
            body["thinking"] = thinking
        if cache_control:
            # Automatic caching: Anthropic places this one on the last cacheable block.
            body["cache_control"] = cache_control
        for key, value in (self.model_args or {}).items():
            if key == "tool_choice":
                choice = to_anthropic_tool_choice(value)
                if choice.get("type") in ("any", "tool") and not profile["forced_tool_choice"]:
                    # This model rejects a forced call; the prompt has to ask for the tool.
                    choice = {"type": "auto"}
                body["tool_choice"] = choice
            elif key in ("max_tokens", "max_completion_tokens"):
                body["max_tokens"] = value
            else:
                body[key] = value
        url, headers = self._request_target(betas)
        return url, headers, body

    async def _atomic_response(self, url: str, headers: dict[str, str], body: dict[str, Any]):
        response = await self._http_post(url, headers, body, stream=False)
        return wrap_json(_completion(response))

    async def _stream_events(self, url: str, headers: dict[str, str], body: dict[str, Any]):
        events = await self._http_post(url, headers, body, stream=True)
        decoder = _StreamDecoder()
        async for event in events:
            chunk = decoder.decode(event)
            if chunk is not None:
                yield wrap_json(chunk)
        _report_transformations(decoder.transformations)
        yield wrap_json(decoder.closing_chunk())

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """Send the conversation to Anthropic; the reply as a MessagePayload."""
        if self.output_mode == "atomic":
            url, headers, body = self._request(messages, stream=False)
            return MessagePayload(
                role="assistant",
                message_coroutine=self._atomic_response(url, headers, body),
                mode="atomic",
            )
        if self.output_mode == "stream":
            url, headers, body = self._request(messages, stream=True)
            return MessagePayload(
                role="assistant",
                message_coroutine=self._stream_events(url, headers, body),
                mode="stream",
            )
        raise ValueError(f"Invalid output mode: {self.output_mode}")
