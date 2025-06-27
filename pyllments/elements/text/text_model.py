from pyllments.base.model_base import Model
import param

class TextModel(Model):
    """Model storing the current text value for TextElement."""

    text = param.String(default="", doc="Current text value handled by the element.")
    payload = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)

    async def handle_payload(self, payload):
        """Store *payload* and ensure its message content is available.

        The helper mirrors the logic used in ``ChatInterfaceModel`` so that the
        *TextElement* can display incoming messages (atomic or streaming)
        without duplicating asyncio plumbing in the view layer.
        """

        # Defer import to avoid a hard dependency at module import time
        from pyllments.payloads.message import MessagePayload  # local import

        self.payload = payload

        if not isinstance(payload, MessagePayload):
            return

        # Rely on MessageModel.aget_message() to handle both atomic and stream cases
        # (it starts streaming if needed and waits for completion, updating
        #  ``content`` incrementally so UI watchers receive live updates).
        try:
            await payload.model.aget_message()
        except AttributeError:
            # No coroutine associated (already atomic & present)
            pass

        # Sync local "text" once content is available (partial updates handled via watchers)
        self.text = payload.model.content
