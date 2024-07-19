import param

from pyllments.base.element_base import Element
from .context_builder_model import ContextBuilderModel

class ContextBuilderElement(Element):
    model = param.ClassSelector(class_=ContextBuilderModel, doc="""
        Model for the context builder""")

    def __init__(self, **params):
        super().__init__(**params)
        self.model = ContextBuilderModel(**params)