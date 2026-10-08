"""
The HTTP transport every REST chat backend shares.

A backend builds its own URL, headers and body; this module sends them, through
the Workers ``fetch`` inside a Cloudflare Worker and the standard library
elsewhere, retries what failed before the first chunk, and turns a streamed
response into the JSON objects of its server-sent events.
"""

import asyncio
import codecs
import json
import urllib.error
import urllib.request
from typing import Any, AsyncIterator

import param

from pyllments.base.model_base import Model

DONE = object()


class _AttrMap:
    """Attribute access over a JSON object so MessageModel can read OpenAI-shaped chunks."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return wrap_json(self._data.get(name))

    def model_dump(self) -> dict[str, Any]:
        return self._data


def wrap_json(value: Any):
    """A chunk dict as the attribute-access object MessageModel reads."""
    if isinstance(value, dict):
        return _AttrMap(value)
    if isinstance(value, list):
        return [wrap_json(item) for item in value]
    return value


def parse_sse_line(line: str):
    """The JSON object on a ``data:`` line, ``DONE`` for ``[DONE]``, or None.

    ``event:`` lines are skipped: every provider here repeats the event name as
    the ``type`` field of its data.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    data = stripped[5:].strip()
    if data == "[DONE]":
        return DONE
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "529", "overload", "timeout", "timed out",
                      "capacity", "temporar", "unavailable", "rate limit", "too many requests")


def is_transient(exc: BaseException) -> bool:
    """A failure worth one more try: the provider was busy or the line dropped, not a bad request."""
    text = str(exc).lower()
    if "400" in text or "bad request" in text or "validation" in text or "401" in text or "403" in text:
        return False
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def js_bytes(value: Any) -> bytes:
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


class HttpChatModel(Model):
    """Base for chat backends that POST JSON to a provider's REST API."""

    transport_retries = param.Integer(
        default=2,
        bounds=(0, None),
        doc=(
            "Retries of a request that failed before its first chunk arrived, on a rate "
            "limit, an overload, a 5xx or a timeout. The model never sees these."
        ),
    )
    retry_backoff = param.Number(default=0.5, doc="Seconds before the first retry; doubles each time")

    error_label = "Chat request failed"

    def _raise_http_error(self, payload: Any, status: int | None = None) -> None:
        prefix = self.error_label
        if status is not None:
            prefix = f"{prefix} ({status})"
        raise ValueError(f"{prefix}: {payload}")

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
                    buffer += decoder.decode(js_bytes(value), final=False)
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
            parsed = parse_sse_line(line)
            if parsed is None:
                continue
            if parsed is DONE:
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
            self._raise_http_error(payload, status)
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
                raise ValueError(f"{self.error_label} ({exc.code}): {err_body}") from exc

        _status, text = await asyncio.to_thread(_call)
        if stream:
            async def _lines():
                for line in text.splitlines():
                    yield line

            return self._iter_sse_payloads(_lines())
        return json.loads(text) if text else {}

    async def _http_post(self, url: str, headers: dict[str, str], body: dict[str, Any], *, stream: bool):
        """POST ``body``; the parsed JSON response, or its events as dicts when ``stream``."""
        try:
            from workers import fetch
        except ImportError:
            fetch = None

        async def attempt():
            if fetch is not None:
                return await self._workers_http_post(fetch, url, headers, body, stream)
            return await self._stdlib_http_post(url, headers, body, stream)

        return await self._with_transport_retries(attempt)

    async def _with_transport_retries(self, attempt):
        """Run ``attempt`` again on a transient failure, with backoff; safe because nothing
        downstream has seen a chunk until it returns."""
        delay = float(self.retry_backoff)
        for tries_left in range(int(self.transport_retries), -1, -1):
            try:
                return await attempt()
            except Exception as exc:
                if tries_left == 0 or not is_transient(exc):
                    raise
                await asyncio.sleep(delay)
                delay *= 2
