from pyllments.base.payload_base import Payload

from .tool_call_model import ToolCallModel


class ToolCallPayload(Payload):
    """
    A payload for tool calls.
    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolCallModel(**params)