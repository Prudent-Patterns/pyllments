import json
from types import SimpleNamespace

import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class MockChatModel(Model):
    """In-process chat backend for tests and Worker mock mode (no HTTP)."""

    model_name = param.String(default="mock")
    tools = param.List(default=None, doc="Provider tool definitions, when the caller forced a tool")
    output_mode = param.Selector(
        objects=["atomic", "stream"],
        default="stream",
        doc="Whether to stream the response or return it all at once",
    )

    @staticmethod
    def _last_user_text(messages: list[MessagePayload]) -> str:
        for payload in reversed(messages):
            if getattr(payload.model, "role", None) == "user":
                return payload.model.content or ""
        return ""

    def _forced_write_card(self, messages: list[MessagePayload]) -> dict | None:
        """Deterministic write_card arguments when that tool is advertised.

        Lets schema-shaped flows run without a provider. The arguments echo the
        user text so tests can see the transcript reached the model.
        """
        names = []
        for tool in self.tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(function, dict) and function.get("name"):
                names.append(function["name"])
        if "write_card" not in names:
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

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        text = f"Mock: {self._last_user_text(messages)}"
        forced = self._forced_write_card(messages)
        if forced is not None:
            return MessagePayload(
                role="assistant",
                content="",
                mode="atomic",
                tool_calls=[forced],
            )
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=text, tool_calls=None)
                )
            ]
        )

        async def _stream():
            yield chunk

        if self.output_mode == "atomic":
            return MessagePayload(role="assistant", content=text, mode="atomic")
        if self.output_mode == "stream":
            return MessagePayload(
                role="assistant",
                message_coroutine=_stream(),
                mode="stream",
            )
        raise ValueError(f"Invalid output mode: {self.output_mode}")
