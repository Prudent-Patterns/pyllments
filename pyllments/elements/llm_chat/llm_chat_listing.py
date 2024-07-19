import param
import panel as pn
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from pyllments.base.listing_base import Listing
from pyllments.elements.llm_chat import LLMChatElement, LLMChatModel


class LLMChatListing(Listing):
    selector = param.ClassSelector(class_=pn.widgets.Select, is_instance=True)
    llm_chat_element = param.ClassSelector(class_=LLMChatElement, is_instance=True)
    chat_model_dict = param.Dict(default={
        'gpt-3.5-turbo': ChatOpenAI,
        'gpt-4o': ChatOpenAI,
        'claude-3-opus-20240229': ChatAnthropic,
    })
    model_args = param.Dict(default={
        'temperature': 0.5
    })
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        default_model_name = next(iter(self.chat_model_dict))
        self.create_llm_chat_element(default_model_name)

    def create_llm_chat_element(self, chat_model_name):
        """Creates and sets the chat model element"""
        llm_chat_model = LLMChatModel(
            model_class=self.chat_model_dict[chat_model_name],
            model_args=self.model_args | {'model_name': chat_model_name}
            )
        self.llm_chat_element = LLMChatElement(llm_chat_model=llm_chat_model)
        return self.llm_chat_element

    def create_selector(self):
        self.selector = pn.widgets.Select(options=list(self.chat_model_dict.keys()))
        self.selector.param.watch(self._on_selector_change, 'value')
        return self.selector
    
    def _on_selector_change(self, event):
        """Callback method triggered when the selector value changes"""
        # print(event)
        self.create_llm_chat_element(event.new)
