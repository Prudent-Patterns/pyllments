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
        models: Optional[Union[list[Union[str, dict]], dict]] = None,  # Allow models as either a list or a dict.
        show_provider_selector: bool = True,
        provider: str = 'OpenAI',
        model: str = 'gpt-4o-mini',
        orientation: Literal['vertical', 'horizontal'] = 'horizontal',
        model_selector_width: int = None,
        provider_selector_width: int = None,
        selector_css: list[str] = [],
        height: int = 57  # Default height in signature is enough
        ) -> pn.widgets.Select | pn.Column | pn.Row:
    
        # Process models input (list or dict) into a standardized dict with inner keys "model" and "base_url".
        def process_models(models_input: Union[list[Union[str, dict]], dict]) -> dict:
            """
            Processes the provided models into a uniform dictionary format.

            For list inputs:
                Each item can be a string or dict. In the dict case, the function uses "model" if present;
                otherwise, it falls back to "name". Optionally, a "display_name" may override the default display.
                e.g.
                [
                    "claude-3-5-sonnet-20240620",
                    "gpt4o-mini",
                    "mistral_chat/mistral-large-latest"
                ]
            For dict inputs:
                The keys are assumed to be display names and the corresponding values are either a dict or a string.
                If the value is a dict, "model" is used (or "name" as a fallback) alongside an optional "base_url".
            e.g.
            {
                "LOCAL DEEPSEEK": {
                    "model": "ollama_chat/deepseek-r1:14b",
                    "base_url": "http://172.17.0.3:11434"
                },
                "OpenAI GPT-4o-mini": {
                    "model": "gpt4o-mini"
                }
            Returns:
                Dictionary mapping unique display names to dictionaries with keys: "model" and "base_url".
            """
            processed = {}
            if isinstance(models_input, dict):
                for display, config in models_input.items():
                    if isinstance(config, dict):
                        model_val = config.get("model") if "model" in config else config.get("name")
                        if not model_val:
                            continue  # Skip entries that lack a model identifier.
                        processed[display] = {"model": model_val, "base_url": config.get("base_url", None)}
                    else:
                        # When the value is directly a string.
                        processed[display] = {"model": config, "base_url": None}
            elif isinstance(models_input, list):
                for item in models_input:
                    if isinstance(item, dict):
                        model_val = item.get("model") if "model" in item else item.get("name")
                        if not model_val:
                            continue
                        display = item.get("display_name") or model_val
                        processed[display] = {"model": model_val, "base_url": item.get("base_url", None)}
                    else:
                        processed[item] = {"model": item, "base_url": None}
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
                self.model.model_name = initial_options[model]["model"]
                self.model.base_url = initial_options[model]["base_url"]
            else:
                initial_option = model_selector.value
                if initial_option:
                    self.model.model_name = initial_option["model"]
                    self.model.base_url = initial_option["base_url"]

            def on_provider_change(event):
                new_options = process_models(provider_map[event.new]) if provider_map[event.new] else {}
                model_selector.options = new_options
                if new_options:
                    first_option = next(iter(new_options.values()))
                    model_selector.value = first_option
                    self.model.model_name = first_option["model"]
                    self.model.base_url = first_option["base_url"]

            provider_selector.param.watch(on_provider_change, 'value')

            def on_model_change(event):
                self.model.model_name = event.new["model"]
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
                self.model.model_name = event.new["model"]
                self.model.base_url = event.new["base_url"]
            model_selector.param.watch(on_model_change, 'value')
            initial_option = model_selector.value
            if initial_option:
                self.model.model_name = initial_option["model"]
                self.model.base_url = initial_option["base_url"]
            return pn.Row(model_selector)

        
