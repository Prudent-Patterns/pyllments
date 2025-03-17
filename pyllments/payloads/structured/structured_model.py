import param

from pyllments.base.model_base import Model


class StructuredModel(Model):
    """
    Model representing structured data.
    """
    data = param.Dict(default={}, doc="The structured data content")

    def __init__(self, **params):
        super().__init__(**params)
        
  