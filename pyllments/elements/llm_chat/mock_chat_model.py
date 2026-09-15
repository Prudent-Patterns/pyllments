from types import SimpleNamespace

import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class MockChatModel(Model):
    """In-process chat backend for tests and Worker mock mode (no HTTP)."""

    model_name = param.String(default="mock")
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

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        text = f"Mock: {self._last_user_text(messages)}"
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
