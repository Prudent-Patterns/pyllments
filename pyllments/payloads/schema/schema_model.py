import param
from pydantic import BaseModel

from pyllments.base.model_base import Model


class SchemaModel(Model):
    """
    Model representing a schema definition.
    
    """
    schema = param.ClassSelector(default=None, class_=BaseModel, doc="The schema definition")

    
    def __init__(self, **params):
        super().__init__(**params)
    