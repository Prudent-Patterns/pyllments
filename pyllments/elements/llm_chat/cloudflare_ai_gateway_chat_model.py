import json
import os
from typing import Any

import param
from dotenv import load_dotenv

from pyllments.elements.llm_chat.http_chat_model import (
    HttpChatModel,
    is_transient as _is_transient,  # noqa: F401  (kept importable here for callers)
    wrap_json as _wrap_json,
)
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.message.chat_completions import to_chat_completions


def _to_plain(value: Any) -> Any:
    """Turn a Workers JS result into dicts and lists the rest of the model can read."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    to_py = getattr(value, "to_py", None)
    if callable(to_py):
        try:
            return _to_plain(to_py())
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    keys = getattr(value, "keys", None)
    if callable(keys):
        try:
            return {str(key): _to_plain(value[key]) for key in list(keys())}
        except Exception:
            pass
    return value


def _completion_from_binding(payload: Any) -> dict[str, Any]:
    """Normalize a binding result onto the chat-completions shape MessageModel reads."""
    plain = _to_plain(payload)
    if isinstance(plain, dict) and plain.get("success") is False:
        raise ValueError(f"Cloudflare AI binding request failed: {plain}")
    if isinstance(plain, dict) and "choices" in plain:
        return plain
    if isinstance(plain, dict) and isinstance(plain.get("result"), dict):
        inner = plain["result"]
        if "choices" in inner:
            return inner
        plain = inner
    text = ""
    tool_calls: list[dict[str, Any]] = []
    if isinstance(plain, dict):
        raw = plain.get("response")
        if raw is None:
            raw = plain.get("content")
        text = raw if isinstance(raw, str) else ""
        tool_calls = _native_tool_calls(plain.get("tool_calls"))
    elif isinstance(plain, str):
        text = plain
    if not tool_calls:
        recovered = _tool_call_written_as_text(text)
        if recovered is not None:
            # A Workers AI model that could not emit a call wrote it as words; the
            # words were never an answer, so they become the call they describe.
            tool_calls, text = _native_tool_calls([recovered]), ""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": text, "tool_calls": tool_calls},
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ]
    }


def _native_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chat-completions messages as the Workers AI binding validates them.

    The binding takes OpenAI's shape for tool calls and tool results, but its
    schema has no null: an assistant message that only called tools carries an
    empty string instead.
    """
    native: list[dict[str, Any]] = []
    for message in messages:
        entry = dict(message)
        if entry.get("content") is None:
            entry["content"] = ""
        native.append(entry)
    return native


def _tool_call_written_as_text(text: str) -> dict[str, Any] | None:
    """``{"name": ..., "parameters"|"arguments": {...}}`` as the whole reply, or None."""
    stripped = (text or "").strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        data = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    arguments = data.get("arguments", data.get("parameters"))
    if not isinstance(arguments, dict):
        return None
    return {"name": data["name"], "arguments": arguments}


def _native_tool_calls(raw: Any) -> list[dict[str, Any]]:
    """Workers AI's ``{name, arguments}`` calls in the chat-completions shape, with ids."""
    calls: list[dict[str, Any]] = []
    for index, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else item
        name = function.get("name")
        if not name:
            continue
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments if arguments is not None else {})
        calls.append(
            {
                "id": item.get("id") or f"call_{index}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        )
    return calls


class CloudflareAIGatewayChatModel(HttpChatModel):
    """Chat model that calls Cloudflare AI Gateway via the REST completions API."""

    model_name = param.String(
        default="openai/gpt-4.1-mini",
        doc="AI Gateway model id (`author/model` or `@cf/author/model`)",
    )
    model_args = param.Dict(
        default={},
        doc="Additional fields merged into the chat completions body",
    )
    output_mode = param.Selector(
        objects=["atomic", "stream"],
        default="stream",
        doc="Whether to stream the response or return it all at once",
    )
    response_format = param.Parameter(
        default=None,
        doc="Response format to pass to the model. Pydantic model or dictionary definition",
    )
    functions = param.Dict(
        default=None,
        doc="Reserved for compatibility. Cloudflare completions uses `tools`.",
    )
    tools = param.List(default=None, doc="List of tools for function calling")
    api_key = param.String(
        default=None,
        allow_None=True,
        doc="Cloudflare API token. Falls back to CLOUDFLARE_API_TOKEN when not provided.",
    )
    account_id = param.String(
        default=None,
        allow_None=True,
        doc="Cloudflare account id. Falls back to CLOUDFLARE_ACCOUNT_ID when not provided.",
    )
    gateway_id = param.String(
        default=None,
        allow_None=True,
        doc="AI Gateway id sent as cf-aig-gateway-id. Defaults to `default`.",
    )
    gateway_headers = param.Dict(
        default={},
        doc="Optional extra request headers, including per-request cf-aig-* overrides",
    )
    client_args = param.Dict(
        default={},
        doc="Optional HTTP extras. `headers` / `defaultHeaders` are merged into the request.",
    )
    ai_binding = param.Parameter(
        default=None,
        doc=(
            "Workers AI binding (env.AI). When set, inference uses binding.run "
            "through the logged-in Wrangler session instead of a REST API token."
        ),
    )
    error_label = "Cloudflare AI Gateway request failed"

    MAJOR_PROVIDER_KEYS = ["openai", "anthropic", "google", "xai", "workers-ai"]
    PROVIDER_KEY_TO_LABEL = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "xai": "xAI",
        "workers-ai": "Workers AI",
        "workers_ai": "Workers AI",
    }
    FALLBACK_MODEL_IDS = [
        "openai/gpt-4.1-mini",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.5-flash",
        "xai/grok-3-mini",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ]

    def _messages_to_completions(self, messages: list[MessagePayload]) -> list[dict[str, Any]]:
        return to_chat_completions(messages)

    @classmethod
    def normalize_model_name(cls, model_name: str) -> str:
        """Normalize optional `workers-ai/` prefix to the `@cf/` catalog form."""
        if model_name.startswith("workers-ai/"):
            rest = model_name.split("/", 1)[1]
            return rest if rest.startswith("@cf/") else f"@cf/{rest}"
        return model_name

    @classmethod
    def _provider_key(cls, model_name: str) -> str | None:
        normalized = cls.normalize_model_name(model_name)
        if normalized.startswith("@cf/"):
            return "workers-ai"
        if "/" not in normalized:
            return None
        return normalized.split("/", 1)[0].lower()

    @classmethod
    def get_provider_model_catalog(
        cls,
        models: dict | list | None = None,
        max_providers: int = 6,
    ) -> dict[str, list[str]]:
        """Return a curated provider -> models catalog for selector rendering."""
        provider_map: dict[str, list[str]] = {}

        def add_model(model_name: str):
            normalized = cls.normalize_model_name(model_name)
            provider_key = cls._provider_key(normalized)
            if not provider_key:
                return
            provider_map.setdefault(provider_key, [])
            if normalized not in provider_map[provider_key]:
                provider_map[provider_key].append(normalized)

        source_models = models if models else cls.FALLBACK_MODEL_IDS
        if isinstance(source_models, dict):
            values_are_collections = any(
                isinstance(value, (list, tuple)) for value in source_models.values()
            )
            if values_are_collections:
                for provider_models in source_models.values():
                    if isinstance(provider_models, (list, tuple)):
                        for model_item in provider_models:
                            add_model(
                                str(model_item.get("model") or model_item.get("name"))
                                if isinstance(model_item, dict)
                                else str(model_item)
                            )
                    else:
                        add_model(str(provider_models))
            else:
                for value in source_models.values():
                    add_model(
                        str(value.get("model") or value.get("name"))
                        if isinstance(value, dict)
                        else str(value)
                    )
        else:
            for model_item in source_models:
                add_model(
                    str(model_item.get("model") or model_item.get("name"))
                    if isinstance(model_item, dict)
                    else str(model_item)
                )

        filtered_map: dict[str, list[str]] = {}
        for provider_key in cls.MAJOR_PROVIDER_KEYS:
            if provider_key in provider_map:
                filtered_map[provider_key] = provider_map[provider_key]
        if not filtered_map:
            for provider_key in sorted(provider_map.keys())[:max_providers]:
                filtered_map[provider_key] = provider_map[provider_key]
        return filtered_map

    @classmethod
    def provider_display_name(cls, provider_key: str) -> str:
        return cls.PROVIDER_KEY_TO_LABEL.get(provider_key.lower(), provider_key.title())

    @classmethod
    def provider_key_for_label(cls, provider_label: str) -> str:
        normalized = provider_label.lower()
        reverse = {value.lower(): key for key, value in cls.PROVIDER_KEY_TO_LABEL.items()}
        return reverse.get(normalized, normalized)

    def _build_request_target(self) -> tuple[str, dict[str, str]]:
        # Resolve token and account at call time so Worker env bindings stay out of import.
        load_dotenv(override=False)
        api_key = self.api_key or os.getenv("CLOUDFLARE_API_TOKEN")
        account_id = self.account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID")
        if not api_key or not account_id:
            raise ValueError(
                "Missing Cloudflare AI Gateway credentials. Set CLOUDFLARE_ACCOUNT_ID "
                "and CLOUDFLARE_API_TOKEN in the environment or .env, or pass "
                "account_id and api_key to LLMChatElement."
            )
        gateway_id = (
            self.gateway_id
            or os.getenv("CLOUDFLARE_AI_GATEWAY_ID")
            or "default"
        )
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/ai/v1/chat/completions"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "cf-aig-gateway-id": gateway_id,
        }
        extra = dict(self.client_args)
        extra_headers = extra.pop("headers", None) or extra.pop("defaultHeaders", None)
        if extra_headers:
            headers.update({str(key): str(value) for key, value in extra_headers.items()})
        if self.gateway_headers:
            headers.update(
                {str(key): str(value) for key, value in self.gateway_headers.items()}
            )
        return url, headers

    def _build_request_body(self, messages: list[MessagePayload], stream: bool) -> dict[str, Any]:
        body = dict(self.model_args)
        body.update({
            "model": self.normalize_model_name(self.model_name),
            "messages": self._messages_to_completions(messages),
            "stream": stream,
        })
        if self.response_format is not None:
            body["response_format"] = self.response_format
        if self.tools:
            body["tools"] = self.tools
        return body

    def _raise_gateway_error(self, payload: Any, status: int | None = None) -> None:
        self._raise_http_error(payload, status)

    def _unwrap_completion(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            self._raise_gateway_error(payload)
        if payload.get("success") is False:
            self._raise_gateway_error(payload.get("errors") or payload.get("error") or payload)
        if "choices" in payload:
            return payload
        result = payload.get("result")
        if isinstance(result, dict) and "choices" in result:
            return result
        self._raise_gateway_error(payload)

    def _binding_inputs(self, body: dict[str, Any]) -> dict[str, Any]:
        # The binding call crosses into JavaScript; only JSON types survive it.
        inputs = json.loads(json.dumps(body))
        inputs.pop("model", None)
        inputs["messages"] = _native_messages(inputs.get("messages") or [])
        # One JSON result. Stream mode below turns that into a single delta.
        # Binding streams are a different shape from the REST SSE parser.
        inputs["stream"] = False
        return inputs

    async def _binding_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        binding = self.ai_binding
        if binding is None:
            raise ValueError("Cloudflare AI binding is not set")
        gateway_id = self.gateway_id or os.getenv("CLOUDFLARE_AI_GATEWAY_ID") or "default"
        inputs = self._binding_inputs(body)
        model_name = self.normalize_model_name(self.model_name)

        async def attempt():
            return await binding.run(model_name, inputs, {"gateway": {"id": gateway_id}})

        result = await self._with_transport_retries(attempt)
        return _completion_from_binding(result)

    async def _atomic_binding_response(self, body: dict[str, Any]):
        return _wrap_json(await self._binding_completion(body))

    async def _stream_binding_events(self, body: dict[str, Any]):
        completion = await self._binding_completion(body)
        message = {}
        choices = completion.get("choices") or []
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or None
        if content or tool_calls:
            yield _wrap_json(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": content or None,
                                "tool_calls": tool_calls,
                            }
                        }
                    ]
                }
            )

    async def _atomic_response(self, body: dict[str, Any]):
        url, headers = self._build_request_target()
        payload = await self._http_post(url, headers, body, stream=False)
        return _wrap_json(self._unwrap_completion(payload))

    async def _stream_events(self, body: dict[str, Any]):
        url, headers = self._build_request_target()
        chunks = await self._http_post(url, headers, body, stream=True)
        async for payload in chunks:
            chunk = self._unwrap_completion(payload) if payload.get("success") is False or "result" in payload else payload
            if not isinstance(chunk, dict) or not chunk.get("choices"):
                continue
            yield _wrap_json(chunk)

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """Generate a response through AI Gateway and package it into MessagePayload.

        The binding path is the Worker session (no API token). REST remains for
        callers that pass account_id and api_key.
        """
        if self.ai_binding is not None:
            body = self._build_request_body(messages, stream=False)
            if self.output_mode == "atomic":
                return MessagePayload(
                    role="assistant",
                    message_coroutine=self._atomic_binding_response(body),
                    mode="atomic",
                )
            if self.output_mode == "stream":
                return MessagePayload(
                    role="assistant",
                    message_coroutine=self._stream_binding_events(body),
                    mode="stream",
                )
            raise ValueError(f"Invalid output mode: {self.output_mode}")
        if self.output_mode == "atomic":
            return MessagePayload(
                role="assistant",
                message_coroutine=self._atomic_response(
                    self._build_request_body(messages, stream=False)
                ),
                mode="atomic",
            )
        if self.output_mode == "stream":
            return MessagePayload(
                role="assistant",
                message_coroutine=self._stream_events(
                    self._build_request_body(messages, stream=True)
                ),
                mode="stream",
            )
        raise ValueError(f"Invalid output mode: {self.output_mode}")
