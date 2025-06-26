from pyllments.base.model_base import Model
import param

class TextModel(Model):
    """Model storing the current text value for TextElement."""

    text = param.String(default="", doc="Current text value handled by the element.")

    def __init__(self, **params):
        super().__init__(**params)
