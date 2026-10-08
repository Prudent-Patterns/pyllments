import param

from pyllments.base.model_base import Model


class SchemaModel(Model):
    """
    Model representing a schema definition.

    ``schema`` is a pydantic model class (``BaseModel`` or ``RootModel``). It is
    typed as a plain parameter so this payload imports without pydantic; the
    elements that build or read a schema import pydantic when they run.
    """
    schema = param.Parameter(default=None, doc="The schema definition: a pydantic model class")

    def __init__(self, **params):
        super().__init__(**params)
