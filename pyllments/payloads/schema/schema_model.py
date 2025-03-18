import param
from pydantic import BaseModel
from pydantic.root_model import RootModel

from pyllments.base.model_base import Model


class SchemaModel(Model):
    """
    Model representing a schema definition.
    
    """
    schema = param.ClassSelector(default=None, class_=(BaseModel, RootModel), is_instance=False,
        doc="The schema definition")

    def __init__(self, **params):
        super().__init__(**params)
    