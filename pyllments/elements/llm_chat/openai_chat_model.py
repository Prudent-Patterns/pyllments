import os
from typing import Any

import param
from dotenv import load_dotenv

from pyllments.elements.llm_chat.http_chat_model import HttpChatModel, wrap_json
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.message.openai_responses import (
    to_responses_input,
    to_responses_text_format,
    to_responses_tool_choice,
    to_responses_tools,
)
from pyllments.payloads.message.usage import usage_record


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    """Responses usage as a usage record; its input_tokens already includes the cached part."""
    details = raw.get("input_tokens_details") or {}
    return usage_record(
        input_tokens=raw.get("input_tokens"),
        cached_input_tokens=details.get("cached_tokens"),
        cache_write_tokens=details.get("cache_write_tokens", raw.get("cache_write_tokens")),
        output_tokens=raw.get("output_tokens"),
    )


def _reasoning(output: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The reply's output items to send back, when it reasoned; None when it did not."""
    if any(item.get("type") == "reasoning" for item in output):
        return {"provider": "openai", "items": output}
    return None


def _output_text(item: dict[str, Any]) -> str:
    return "".join(
        part.get("text", "")
        for part in item.get("content") or []
        if part.get("type") in ("output_text", "refusal")
    ) if item.get("type") == "message" else ""


def _completion(response: dict[str, Any]) -> dict[str, Any]:
    """A non-streamed Responses result in the chat-completions shape MessageModel reads."""
    if response.get("status") == "failed":
        raise ValueError(f"OpenAI response failed: {response.get('error')}")
    output = response.get("output") or []
    tool_calls = [
        {
            "id": item.get("call_id"),
            "type": "function",
            "function": {"name": item.get("name"), "arguments": item.get("arguments") or ""},
        }
        for item in output
        if item.get("type") == "function_call"
    ]
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "".join(_output_text(item) for item in output),
                "tool_calls": tool_calls,
            }
        }],
        "usage": _usage(response.get("usage") or {}),
        "reasoning": _reasoning(output),
    }


class _StreamDecoder:
    """Responses stream events as chat-completions chunks."""

    def __init__(self):
        self.tool_index: dict[str, int] = {}
        self.response: dict[str, Any] | None = None

    @staticmethod
    def _chunk(delta: dict[str, Any]) -> dict[str, Any]:
        return {"choices": [{"delta": delta}]}

    def decode(self, event: dict[str, Any]) -> dict[str, Any] | None:
        kind = event.get("type")
        if kind in ("response.output_text.delta", "response.refusal.delta"):
            return self._chunk({"content": event.get("delta", "")})
        if kind == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") == "function_call":
                self.tool_index[item.get("id")] = len(self.tool_index)
                return self._chunk({"tool_calls": [{
                    "index": self.tool_index[item.get("id")],
                    "id": item.get("call_id"),
                    "type": "function",
                    "function": {"name": item.get("name"), "arguments": item.get("arguments") or ""},
                }]})
        elif kind == "response.function_call_arguments.delta":
            index = self.tool_index.get(event.get("item_id"))
            if index is not None and event.get("delta"):
                return self._chunk({"tool_calls": [{"index": index, "function": {"arguments": event["delta"]}}]})
        elif kind in ("response.completed", "response.incomplete"):
            self.response = event.get("response") or {}
        elif kind == "response.failed":
            error = (event.get("response") or {}).get("error")
            raise ValueError(f"OpenAI response failed: {error}")
        elif kind == "error":
            raise ValueError(f"OpenAI stream error: {event.get('error') or event.get('message')}")
        return None

    def closing_chunk(self) -> dict[str, Any]:
        response = self.response or {}
        return {
            "choices": [],
            "usage": _usage(response.get("usage") or {}),
            "reasoning": _reasoning(response.get("output") or []),
        }


class OpenAIChatModel(HttpChatModel):
    """
    Chat model that calls OpenAI's Responses API directly, statelessly.

    ``store`` is off, so OpenAI keeps nothing between requests and every request
    carries the whole conversation. Caching is automatic on OpenAI's side.
    Encrypted reasoning comes back with each reply (``include_reasoning``); a
    reply that reasoned keeps its output items in its ``reasoning`` and is
    sent back with them (the history keeps them for the turn). ``base_url`` points it at another
    host that speaks the Responses API.
    """

    model_name = param.String(default="gpt-5.5", doc="OpenAI model id")
    model_args = param.Dict(
        default={},
        doc=(
            "Extra request fields, e.g. ``reasoning``. A chat-completions "
            "``tool_choice`` is translated and ``max_tokens`` becomes ``max_output_tokens``."
        ),
    )
    output_mode = param.Selector(
        objects=["atomic", "stream"],
        default="stream",
        doc="Whether to stream the response or return it all at once",
    )
    response_format = param.Parameter(
        default=None,
        doc="Chat-completions response_format; sent as the Responses ``text.format``",
    )
    tools = param.List(default=None, doc="Chat-completions function tools; sent in the Responses form")
    api_key = param.String(
        default=None,
        allow_None=True,
        doc="OpenAI API key. Falls back to OPENAI_API_KEY when not provided.",
    )
    base_url = param.String(default="https://api.openai.com/v1", doc="API root, including /v1")
    include_reasoning = param.Boolean(
        default=True,
        doc="Ask for encrypted reasoning so a reply's reasoning can be sent back",
    )
    prompt_cache_key = param.String(
        default=None,
        allow_None=True,
        doc="Optional key grouping requests that share a prompt, for cache routing and accounting",
    )
    headers = param.Dict(default={}, doc="Extra request headers")

    error_label = "OpenAI request failed"

    def _request_target(self) -> tuple[str, dict[str, str]]:
        load_dotenv(override=False)
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing OpenAI API key. Set OPENAI_API_KEY in the environment or "
                ".env, or pass api_key to LLMChatElement."
            )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        headers.update({str(key): str(value) for key, value in self.headers.items()})
        return f"{self.base_url.rstrip('/')}/responses", headers

    def _request(self, messages: list[MessagePayload], stream: bool) -> tuple[str, dict[str, str], dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model_name,
            "input": to_responses_input(messages),
            "stream": stream,
            "store": False,
        }
        if self.include_reasoning:
            body["include"] = ["reasoning.encrypted_content"]
        if self.tools:
            body["tools"] = to_responses_tools(self.tools)
        text_format = to_responses_text_format(self.response_format)
        if text_format is not None:
            body["text"] = {"format": text_format}
        if self.prompt_cache_key:
            body["prompt_cache_key"] = self.prompt_cache_key
        for key, value in (self.model_args or {}).items():
            if key == "tool_choice":
                body["tool_choice"] = to_responses_tool_choice(value)
            elif key in ("max_tokens", "max_completion_tokens"):
                body["max_output_tokens"] = value
            else:
                body[key] = value
        url, headers = self._request_target()
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
        yield wrap_json(decoder.closing_chunk())

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """Send the conversation to OpenAI; the reply as a MessagePayload."""
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
