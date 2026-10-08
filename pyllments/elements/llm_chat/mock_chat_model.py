import json
from types import SimpleNamespace
from typing import Any

import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload
from pyllments.payloads.message.chat_completions import to_chat_completions


class MockChatModel(Model):
    """
    In-process chat backend for tests and Worker mock mode (no HTTP).

    Plays a ``script`` of replies, one per request, in OpenAI's streaming or
    atomic shape, so a flow with tool rounds runs end to end without a
    provider. Each request's ``messages`` list is kept in ``requests``, which is
    how a test checks what the model was shown.
    """

    model_name = param.String(default="mock")
    model_args = param.Dict(default={}, doc="Request options, as a real backend would merge them")
    tools = param.List(default=None, doc="Provider tool definitions, when the caller forced a tool")
    output_mode = param.Selector(
        objects=["atomic", "stream"],
        default="stream",
        doc="Whether to stream the response or return it all at once",
    )
    script = param.List(
        default=None,
        doc=(
            "Replies to play in order, one per request. Each is a str, or a dict "
            "``{'content': str, 'tool_calls': [{'name', 'arguments', 'id'?}]}`` "
            "with ``arguments`` as a dict, or ``{'error': str}`` for a request that "
            "fails at the provider. Past the end, the echo reply plays."
        ),
    )
    requests = param.List(
        default=[],
        doc="The chat-completions ``messages`` of every request so far, oldest first.",
    )
    request_args = param.List(
        default=[],
        doc="The ``model_args`` in force for every request so far, oldest first.",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._script_position = 0
        self._call_counter = 0

    @staticmethod
    def _last_user_text(messages: list[MessagePayload]) -> str:
        for payload in reversed(messages):
            if getattr(payload.model, "role", None) == "user":
                return payload.model.content or ""
        return ""

    def _advertised_tool_names(self) -> list[str]:
        names = []
        for tool in self.tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(function, dict) and function.get("name"):
                names.append(function["name"])
        return names

    def _forced_write_card(self, messages: list[MessagePayload]) -> dict | None:
        """Deterministic write_card arguments when that tool is advertised.

        Lets schema-shaped flows run without a provider. The arguments echo the
        user text so tests can see the transcript reached the model.
        """
        if "write_card" not in self._advertised_tool_names():
            return None
        text = self._last_user_text(messages).strip()
        return {
            "id": "call_mock_write_card",
            "type": "function",
            "function": {
                "name": "write_card",
                "arguments": json.dumps(
                    {
                        "title": (text[:60] or "Conversation"),
                        "summary": text[:500] or "No messages.",
                        "outcome": None,
                        "record": {"version": 1, "topics": [], "open_questions": []},
                    }
                ),
            },
        }

    def _wire_tool_call(self, call: dict[str, Any]) -> dict[str, Any]:
        self._call_counter += 1
        arguments = call.get("arguments", {})
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        return {
            "id": call.get("id") or f"call_mock_{self._call_counter}",
            "type": "function",
            "function": {"name": call["name"], "arguments": arguments},
        }

    def _next_reply(self, messages: list[MessagePayload]) -> tuple[str, list[dict[str, Any]]]:
        """The next scripted reply as (content, wire tool calls)."""
        if self.script and self._script_position < len(self.script):
            step = self.script[self._script_position]
            self._script_position += 1
            if isinstance(step, str):
                return step, []
            calls = [self._wire_tool_call(call) for call in step.get("tool_calls") or []]
            return step.get("content") or "", calls
        forced = self._forced_write_card(messages)
        if forced is not None:
            return "", [forced]
        return f"Mock: {self._last_user_text(messages)}", []

    @staticmethod
    def _text_chunks(text: str):
        # Two chunks when there is room, so stream consumers see more than one token.
        if len(text) > 8:
            half = len(text) // 2
            parts = [text[:half], text[half:]]
        else:
            parts = [text] if text else []
        for part in parts:
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=part, tool_calls=None))]
            )

    @staticmethod
    def _tool_call_chunk(index: int, call: dict[str, Any]):
        delta = SimpleNamespace(
            index=index,
            id=call["id"],
            type="function",
            function=SimpleNamespace(
                name=call["function"]["name"],
                arguments=call["function"]["arguments"],
            ),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[delta]))]
        )

    def _next_failure(self) -> str | None:
        step = self.script[self._script_position] if self.script and self._script_position < len(self.script) else None
        if isinstance(step, dict) and "error" in step:
            self._script_position += 1
            return str(step["error"])
        return None

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        self.requests = [*self.requests, to_chat_completions(messages)]
        self.request_args = [*self.request_args, dict(self.model_args or {})]
        failure = self._next_failure()
        if failure is not None:
            # The provider failed: an atomic reply raises when awaited, a stream raises on its first chunk.
            async def _fail():
                raise RuntimeError(failure)

            async def _failing_stream():
                raise RuntimeError(failure)
                yield  # noqa: unreachable - makes this an async generator

            if self.output_mode == "atomic":
                return MessagePayload(role="assistant", message_coroutine=_fail(), mode="atomic")
            return MessagePayload(role="assistant", message_coroutine=_failing_stream(), mode="stream")
        text, tool_calls = self._next_reply(messages)

        if self.output_mode == "atomic":
            return MessagePayload(
                role="assistant",
                content=text,
                mode="atomic",
                tool_calls=tool_calls,
            )
        if self.output_mode == "stream":
            chunks = [
                *self._text_chunks(text),
                *(self._tool_call_chunk(i, call) for i, call in enumerate(tool_calls)),
            ]

            async def _stream():
                for chunk in chunks:
                    yield chunk

            return MessagePayload(
                role="assistant",
                message_coroutine=_stream(),
                mode="stream",
            )
        raise ValueError(f"Invalid output mode: {self.output_mode}")
