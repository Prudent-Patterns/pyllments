from pyllments.base.payload_base import Payload

from .tool_list_model import ToolListModel

class ToolListPayload(Payload):
    def __init__(self, **params):
        super().__init__(**params)
        self.model = ToolListModel(**params)