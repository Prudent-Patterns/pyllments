from pyllments.base.payload_base import Payload

from .schema_model import SchemaModel


class SchemaPayload(Payload):
    """
    A payload for schema definitions.
    
    This payload encapsulates a schema definition that can be used to validate
    structured data. It provides methods for schema validation, manipulation,
    and example generation.
    """
    def __init__(self, **params):
        super().__init__(**params)
        self.model = SchemaModel(**params)