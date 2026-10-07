import asyncio
import codecs
import json
import os
import urllib.error
import urllib.request
from typing import Any, AsyncIterator

import param
from dotenv import load_dotenv

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.message.chat_completions import to_chat_completions

_DONE = object()


class _AttrMap:
    """Attribute access over a JSON object so MessageModel can read OpenAI-shaped chunks."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _wrap_json(self._data.get(name))

    def model_dump(self) -> dict[str, Any]:
        return self._data


def _wrap_json(value: Any):
    if isinstance(value, dict):
        return _AttrMap(value)
    if isinstance(value, list):
        return [_wrap_json(item) for item in value]
    return value


def _parse_sse_line(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    data = stripped[5:].strip()
    if data == "[DONE]":
        return _DONE
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


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
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": text, "tool_calls": tool_calls},
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ]
    }


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


def _js_bytes(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if hasattr(value, "to_py"):
        converted = value.to_py()
        if isinstance(converted, (bytes, bytearray, memoryview)):
            return bytes(converted)
        try:
            return bytes(converted)
        except Exception:
            pass
    return bytes(value)


class CloudflareAIGatewayChatModel(Model):
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
        prefix = "Cloudflare AI Gateway request failed"
        if status is not None:
            prefix = f"{prefix} ({status})"
        raise ValueError(f"{prefix}: {payload}")

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

    async def _iter_response_lines(self, response) -> AsyncIterator[str]:
        body = getattr(response, "body", None)
        get_reader = getattr(body, "getReader", None) if body is not None else None
        if get_reader is None:
            text = await response.text()
            for line in text.splitlines():
                yield line
            return

        reader = get_reader()
        decoder = codecs.getincrementaldecoder("utf-8")()
        buffer = ""
        try:
            while True:
                chunk = await reader.read()
                done = bool(getattr(chunk, "done", False))
                value = getattr(chunk, "value", None)
                if value is not None:
                    buffer += decoder.decode(_js_bytes(value), final=False)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    yield line.rstrip("\r")
                if done:
                    buffer += decoder.decode(b"", final=True)
                    if buffer:
                        yield buffer.rstrip("\r")
                    break
        finally:
            cancel = getattr(reader, "cancel", None)
            if cancel is not None:
                try:
                    await cancel()
                except Exception:
                    pass

    async def _iter_sse_payloads(self, lines: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
        async for line in lines:
            parsed = _parse_sse_line(line)
            if parsed is None:
                continue
            if parsed is _DONE:
                break
            yield parsed

    async def _workers_http_post(self, fetch, url: str, headers: dict[str, str], body: dict[str, Any], stream: bool):
        response = await fetch(
            url,
            method="POST",
            headers=headers,
            body=json.dumps(body),
        )
        status = int(getattr(response, "status", 0) or 0)
        if status >= 400:
            text = await response.text()
            try:
                payload = json.loads(text) if text else text
            except json.JSONDecodeError:
                payload = text
            self._raise_gateway_error(payload, status)
        if stream:
            return self._iter_sse_payloads(self._iter_response_lines(response))
        text = await response.text()
        return json.loads(text) if text else {}

    async def _stdlib_http_post(self, url: str, headers: dict[str, str], body: dict[str, Any], stream: bool):
        def _call() -> tuple[int, str]:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request) as response:
                    return int(response.status), response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise ValueError(
                    f"Cloudflare AI Gateway request failed ({exc.code}): {err_body}"
                ) from exc

        _status, text = await asyncio.to_thread(_call)
        if stream:
            async def _lines():
                for line in text.splitlines():
                    yield line

            return self._iter_sse_payloads(_lines())
        return json.loads(text) if text else {}

    async def _http_post(self, url: str, headers: dict[str, str], body: dict[str, Any], *, stream: bool):
        try:
            from workers import fetch
        except ImportError:
            fetch = None
        if fetch is not None:
            return await self._workers_http_post(fetch, url, headers, body, stream)
        return await self._stdlib_http_post(url, headers, body, stream)

    def _binding_inputs(self, body: dict[str, Any]) -> dict[str, Any]:
        # The binding call crosses into JavaScript; only JSON types survive it.
        inputs = json.loads(json.dumps(body))
        inputs.pop("model", None)
        # One JSON result. Stream mode below turns that into a single delta.
        # Binding streams are a different shape from the REST SSE parser.
        inputs["stream"] = False
        return inputs

    async def _binding_completion(self, body: dict[str, Any]) -> dict[str, Any]:
        binding = self.ai_binding
        if binding is None:
            raise ValueError("Cloudflare AI binding is not set")
        gateway_id = self.gateway_id or os.getenv("CLOUDFLARE_AI_GATEWAY_ID") or "default"
        result = await binding.run(
            self.normalize_model_name(self.model_name),
            self._binding_inputs(body),
            {"gateway": {"id": gateway_id}},
        )
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
