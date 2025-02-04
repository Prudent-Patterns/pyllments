from typing import Literal, Union, Optional

import panel as pn
import param
from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.payloads.message import MessagePayload
from pyllments.elements.llm_chat import LLMChatModel


class LLMChatElement(Element):
    """Responsible for using LLMs to respond to messages and sets of messages"""
    model_selector_view = param.ClassSelector(class_=(pn.widgets.Select, pn.Column, pn.Row))
    
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
        models: Optional[list[Union[str, dict]]] = None,
        show_provider_selector: bool = True,
        provider: str = 'OpenAI',
        model: str = 'gpt-4o-mini',
        orientation: Literal['vertical', 'horizontal'] = 'horizontal',
        model_selector_width: int = None,
        provider_selector_width: int = None,
        selector_css: list[str] = [],
        height: int = 57  # Default height in signature is enough
        ) -> pn.widgets.Select | pn.Column | pn.Row:
    
        # Helper to process models into a standardized dict with keys "name", "base_url"
        def process_models(models_list: list[Union[str, dict]]) -> dict:
            """
            Processes a list of models into a standardized dictionary format with unique display names.
            
            Each model is represented as a dictionary with keys "name" and "base_url".
            The dictionary is keyed by the display name, which is derived from the "display_name" field
            if available, or it falls back to the model's "name".

            Note:
                - Display names must be unique, since they are used as dictionary keys.
                  If multiple models share the same display name, later entries will override earlier ones.
                - The "base_url" is defaulted to None if it is not provided.
            """
            processed = {}
            for item in models_list:
                if isinstance(item, dict):
                    # "name" is required; "display_name" is optional.
                    name_val = item.get("name")
                    if not name_val:
                        continue  # Skip models without a mandatory 'name'.
                    # Determine the display name: use "display_name" when available, otherwise use the model's "name".
                    display = item.get("display_name") or name_val
                    base_url_val = item.get("base_url", None)  # Default to None if base_url isn't provided.
                    # Note: Duplicate display names will be overwritten.
                    processed[display] = {"name": name_val, "base_url": base_url_val}
                else:
                    # String items are treated as the model's "name"; display name is the same and base_url is None.
                    processed[item] = {"name": item, "base_url": None}
            return processed

        if show_provider_selector:
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
            if models is not None:
                provider_map['Custom'] = models

            provider_selector = pn.widgets.Select(
                name='Provider Selector',
                value=provider,
                options=list(provider_map.keys()),
                stylesheets=selector_css,
                width=provider_selector_width,
                sizing_mode='stretch_width',
                margin=0
            )
            
            initial_options = process_models(provider_map[provider_selector.value]) if provider_map[provider_selector.value] else {}
            model_selector = pn.widgets.Select(
                name='Model Selector',
                options=initial_options,
                stylesheets=selector_css,
                width=model_selector_width,
                sizing_mode='stretch_width',
                margin=0,
            )

            if model in initial_options:
                model_selector.value = initial_options[model]
                self.model.model_name = initial_options[model]["name"]
                self.model.base_url = initial_options[model]["base_url"]
            else:
                initial_option = model_selector.value
                if initial_option:
                    self.model.model_name = initial_option["name"]
                    self.model.base_url = initial_option["base_url"]

            def on_provider_change(event):
                new_options = process_models(provider_map[event.new]) if provider_map[event.new] else {}
                model_selector.options = new_options
                if new_options:
                    first_option = next(iter(new_options.values()))
                    model_selector.value = first_option
                    self.model.model_name = first_option["name"]
                    self.model.base_url = first_option["base_url"]

            provider_selector.param.watch(on_provider_change, 'value')

            def on_model_change(event):
                self.model.model_name = event.new["name"]
                self.model.base_url = event.new["base_url"]

            model_selector.param.watch(on_model_change, 'value')
            self.model_selector_view = pn.Row(provider_selector, pn.Spacer(width=10), model_selector)
            return self.model_selector_view
        else:
            import litellm
            if models is None:
                models = litellm.open_ai_chat_completion_models
            options = process_models(models)
            model_selector = pn.widgets.Select(
                name='Model Selector',
                options=options,
                stylesheets=selector_css,
                sizing_mode='stretch_width',
                margin=0
            )
            def on_model_change(event):
                self.model.model_name = event.new["name"]
                self.model.base_url = event.new["base_url"]
            model_selector.param.watch(on_model_change, 'value')
            initial_option = model_selector.value
            if initial_option:
                self.model.model_name = initial_option["name"]
                self.model.base_url = initial_option["base_url"]
            return pn.Row(model_selector)

        
