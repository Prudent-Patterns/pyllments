from pyllments.base.model_base import Model
import param

class TextModel(Model):
    """Model storing the current text value for TextElement."""

    text = param.String(default="", doc="Current text value handled by the element.")
    payload = param.Parameter(default=None)

    def __init__(self, **params):
        super().__init__(**params)

    async def handle_payload(self, payload):
        """Store payload and trigger streaming - let views handle display."""
        # Just store the payload - views will watch it directly
        self.payload = payload

        # Start streaming if needed - payload will update its own content
        if payload and hasattr(payload.model, 'aget_message'):
            try:
                await payload.model.aget_message()
            except AttributeError:
                pass
