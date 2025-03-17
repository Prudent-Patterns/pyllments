from pyllments.base.payload_base import Payload

from .structured_model import StructuredModel


class StructuredPayload(Payload):
    """
    A payload for passing schemas.

    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = StructuredModel(**params)
    
   