from pyllments.base.payload_base import Payload

from .tool_response_model import ToolResponseModel


class ToolResponsePayload(Payload):
    """
    A payload for tool calls.
    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolResponseModel(**params)