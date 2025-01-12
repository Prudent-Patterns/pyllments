from typing import Literal, Union

import panel as pn

from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.payloads.message import MessagePayload
from pyllments.elements.llm_chat import LLMChatModel


class LLMChatElement(Element):
    """Responsible for using LLMs to respond to messages and sets of messages"""
    def __init__(self, **params):
        super().__init__(**params)

        self.model = LLMChatModel(**params)
        self._message_output_setup()
        self._messages_input_setup()
        
    def _message_output_setup(self):
        def pack(message_payload: MessagePayload) -> MessagePayload:
            return message_payload
            
        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _messages_input_setup(self):
        def unpack(payload: Union[list[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            response = self.model.generate_response(payloads)
            self.ports.output['message_output'].stage_emit(message_payload=response)

        self.ports.add_input(name='messages_input', unpack_payload_callback=unpack)

    @Component.view
    def create_model_selector_view(
        self,
        models: list[str] = None,
        orientation: Literal['vertical', 'horizontal'] = 'horizontal',
        model_selector_width: int = None,
        provider_selector_width: int = None,
        selector_css: list[str] = [],
        ) -> pn.widgets.Select | pn.Column | pn.Row:
    
        if models:
            model_selector = pn.widgets.Select(
                name='Model Selector',
                stylesheets=selector_css,
                options=models,
                sizing_mode='stretch_width',
                margin=0)
            def on_model_change(event):
                self.model.model_name = event.new
            model_selector.param.watch(on_model_change, 'value')
            self.model.model_name = model_selector.value
            return pn.Row(model_selector)
        else:
            import litellm

            provider_map = {
                'OpenAI': litellm.open_ai_chat_completion_models,
                'Anthropic': litellm.anthropic_models,
                'Gemini': litellm.gemini_models,
                'XAI': litellm.xai_models,
                'Groq': litellm.groq_models,
                'Mistral': litellm.mistral_chat_models,
                'OpenRouter': litellm.openrouter_models
            }
            provider_selector = pn.widgets.Select(
                name='Provider Selector',
                value='OpenAI',
                options=list(provider_map.keys()),
                stylesheets=selector_css,
                width=provider_selector_width,
                sizing_mode='stretch_width',
                margin=0
                )
            model_selector = pn.widgets.Select(
                name='Model Selector',
                options=provider_map[provider_selector.value],
                stylesheets=selector_css,
                width=model_selector_width,
                sizing_mode='stretch_width',
                margin=0
                )
            self.model.model_name = model_selector.value

            def on_provider_change(event):
                model_selector.options = provider_map[event.new]
            provider_selector.param.watch(on_provider_change, 'value')
            def on_model_change(event):
                self.model.model_name = event.new
            model_selector.param.watch(on_model_change, 'value')
            return pn.Row(provider_selector, pn.Spacer(width=10), model_selector)
