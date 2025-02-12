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
        self._messages_emit_input_setup()
        
    def _message_output_setup(self):
        def pack(message_payload: MessagePayload) -> MessagePayload:
            return message_payload
            
        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _messages_emit_input_setup(self):
        def unpack(payload: Union[list[MessagePayload], MessagePayload]):
            payloads = [payload] if not isinstance(payload, list) else payload
            response = self.model.generate_response(payloads)
            self.ports.output['message_output'].stage_emit(message_payload=response)

        self.ports.add_input(name='messages_emit_input', unpack_payload_callback=unpack)

    @Component.view
    def create_model_selector_view(
        self,
        models: Optional[Union[list[Union[str, dict]], dict]] = None,
        show_provider_selector: bool = True,
        provider: str = 'OpenAI',
        model: Union[str, dict] = 'gpt-4o-mini',
        orientation: Literal['vertical', 'horizontal'] = 'horizontal',
        model_selector_width: int = None,
        provider_selector_width: int = None,
        selector_css: list[str] = [],
        height: int = 57
    ) -> Union[pn.widgets.Select, pn.Column, pn.Row]:
        """
        Creates a view for selecting an LLM model, optionally including a provider selector.

        This implementation simplifies the processing of the models input by first normalizing
        it into a standard mapping of display names to model configurations, which simplifies
        subsequent widget setup and state management.

        Parameters
        ----------
        models : list or dict, optional
            A list or dict of models. If a dict, the keys are used as display names.
        show_provider_selector : bool, default True
            Whether to include a provider selection widget.
        provider : str, default 'OpenAI'
            The default provider value.
        model : str or dict, default 'gpt-4o-mini'
            The default model (this update assumes it is a string to be pre-selected).
        orientation : {'vertical', 'horizontal'}, default 'horizontal'
            Layout orientation for the provider and model selectors.
        model_selector_width : int, optional
            Optional width for the model selector widget.
        provider_selector_width : int, optional
            Optional width for the provider selector widget.
        selector_css : list of str, default []
            Optional CSS stylesheets to be applied to the selectors.
        height : int, default 57
            The default height for the view, mainly for UI spacing.

        Returns
        -------
        pn.widgets.Select or pn.Column or pn.Row
            A Panel widget (or layout) representing the selector view.
        """
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
            normalized = []
            if isinstance(models_input, dict):
                for display, value in models_input.items():
                    if isinstance(value, dict):
                        model_val = value.get("model") or value.get("name")
                        if not model_val:
                            continue
                        normalized.append({
                            "display_name": value.get("display_name", display),
                            "model": model_val,
                            "base_url": value.get("base_url")
                        })
                    else:
                        normalized.append({
                            "display_name": display,
                            "model": value,
                            "base_url": None
                        })
            elif isinstance(models_input, list):
                for item in models_input:
                    if isinstance(item, dict):
                        model_val = item.get("model") or item.get("name")
                        if not model_val:
                            continue
                        normalized.append({
                            "display_name": item.get("display_name", model_val),
                            "model": model_val,
                            "base_url": item.get("base_url")
                        })
                    else:
                        normalized.append({
                            "display_name": item,
                            "model": item,
                            "base_url": None
                        })
            return {
                entry["display_name"]: {"model": entry["model"], "base_url": entry["base_url"]}
                for entry in normalized
            }

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
            # Allow for custom models via the passed-in models argument.
            if models:
                provider_map['Custom'] = models

            # NEW: Determine the default provider based on the provided default model string.
            default_provider = provider  # Fallback to the provided 'provider'
            default_model_config = None
            if isinstance(model, str):
                for prov, models_list in provider_map.items():
                    processed_models = process_models(models_list)
                    if model in processed_models:
                        default_provider = prov
                        default_model_config = processed_models[model]
                        break

            # Create a provider selector widget using the determined default_provider.
            provider_selector = pn.widgets.Select(
                name='Provider Selector',
                value=default_provider,
                options=list(provider_map.keys()),
                stylesheets=selector_css,
                width=provider_selector_width,
                sizing_mode='stretch_width',
                margin=0
            )

            # Initialize model options based on the selected provider.
            initial_options = process_models(provider_map.get(default_provider, {}))
            model_selector = pn.widgets.Select(
                name='Model Selector',
                options=initial_options,
                stylesheets=selector_css,
                width=model_selector_width,
                sizing_mode='stretch_width',
                margin=0,
            )

            # Function to set the default model selection—matching by default_model_config if available.
            def set_model_defaults():
                if default_model_config is not None:
                    model_selector.value = default_model_config
                    self.model.model_name = default_model_config["model"]
                    self.model.base_url = default_model_config["base_url"]
                else:
                    selected_config = None
                    if isinstance(model, dict):
                        # Try to find a configuration that matches the provided dict.
                        for config in initial_options.values():
                            if config == model:
                                selected_config = config
                                break
                    else:
                        selected_config = initial_options.get(model)
                    
                    if selected_config:
                        model_selector.value = selected_config
                        self.model.model_name = selected_config["model"]
                        self.model.base_url = selected_config["base_url"]

            set_model_defaults()

            # Update available models when the provider changes.
            def on_provider_change(event):
                new_options = process_models(provider_map.get(event.new, {}))
                model_selector.options = new_options
                # Try to set the default model for this new provider.
                default_cfg = None
                for cfg in new_options.values():
                    if cfg["model"] == model:
                        default_cfg = cfg
                        break
                if default_cfg is None and new_options:
                    default_cfg = next(iter(new_options.values()))
                model_selector.value = default_cfg
                if default_cfg:
                    self.model.model_name = default_cfg["model"]
                    self.model.base_url = default_cfg["base_url"]

            provider_selector.param.watch(on_provider_change, 'value')

            # Update the underlying model when model selection changes.
            def on_model_change(event):
                self.model.model_name = event.new["model"]
                self.model.base_url = event.new["base_url"]

            model_selector.param.watch(on_model_change, 'value')

            # Construct the overall layout based on requested orientation.
            if orientation == 'vertical':
                self.model_selector_view = pn.Column(provider_selector, model_selector)
            else:
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
            # NEW: Set the default model based on the passed 'model' argument.
            default_config = options.get(model)
            if default_config is not None:
                model_selector.value = default_config
                self.model.model_name = default_config["model"]
                self.model.base_url = default_config["base_url"]

            def on_model_change(event):
                self.model.model_name = event.new["model"]
                self.model.base_url = event.new["base_url"]

            model_selector.param.watch(on_model_change, 'value')
            return pn.Row(model_selector)    