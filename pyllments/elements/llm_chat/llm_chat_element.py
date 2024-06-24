import param
import panel as pn

from pyllments.base import Element
from pyllments.elements.llm_chat import LLMChatModel

class LLMChatElement(Element):
    model = param.ClassSelector(class_=LLMChatModel)

    temperature = param.Number(default=0.5)
    temperature_view = param.ClassSelector(class_=pn.widgets.FloatSlider, is_instance=True)

    def __init__(self, **params):
        super().__init__(**params)

    def create_temperature_view(self, **kwargs):
        self.temperature_view = pn.widgets.FloatSlider(**kwargs)
        return self.temperature_view
