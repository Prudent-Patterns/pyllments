from __future__ import annotations

from typing import Literal, Union, Optional, List, TYPE_CHECKING, cast

import param
from pyllments.base.element_base import Element
from pyllments.base.component_base import Component
from pyllments.payloads import MessagePayload, ToolsResponsePayload, StructuredPayload
from pyllments.elements.llm_chat.openrouter_chat_model import OpenRouterChatModel
from pyllments.elements.llm_chat.litellm_chat_model import LiteLLMChatModel

if TYPE_CHECKING:
    import panel as pn


class LLMChatElement(Element):
    """Responsible for using LLMs to respond to messages and sets of messages"""

    backend = param.Selector(
        objects=['openrouter', 'litellm'],
        default='openrouter',
        doc="Chat backend model implementation")
    generate_content_on_emit = param.Boolean(default=False, doc="Whether to generate and populate the full message content before emitting it")

    def __init__(self, **params):
        super().__init__(**params)
        self.model_selector_view = None

        # Keep model construction explicit so backend swapping remains transparent.
        self._model_init_params = self._extract_model_params(params)
        self.model = self._create_model(self.backend, self._model_init_params)
        self.param.watch(self._on_backend_change, 'backend')
        self._message_output_setup()
        self._messages_emit_input_setup()
        self._tools_input_setup()

    def _extract_model_params(self, params: dict) -> dict:
        element_param_names = {'backend', 'generate_content_on_emit'}
        return {
            key: value
            for key, value in params.items()
            if key not in element_param_names
        }

    def _capture_model_state(self) -> dict:
        state = {}
        for key in ['model_name', 'model_args', 'output_mode', 'response_format', 'functions', 'tools', 'api_key', 'client_args']:
            if hasattr(self.model, key):
                state[key] = getattr(self.model, key)
        if hasattr(self.model, 'base_url'):
            state['base_url'] = getattr(self.model, 'base_url')
        return state

    def _filter_model_params(self, model_cls, model_params: dict) -> dict:
        accepted_params = set(model_cls.param.objects().keys())
        return {
            key: value
            for key, value in model_params.items()
            if key in accepted_params
        }

    def _create_model(self, backend: str, model_params: dict):
        if backend == 'openrouter':
            params = dict(model_params)
            params.pop('base_url', None)
            return OpenRouterChatModel(**self._filter_model_params(OpenRouterChatModel, params))
        if backend == 'litellm':
            return LiteLLMChatModel(**self._filter_model_params(LiteLLMChatModel, model_params))
        raise ValueError(f"Unsupported LLM backend: {backend}")

    def _on_backend_change(self, event):
        replacement_params = dict(self._model_init_params)
        replacement_params.update(self._capture_model_state())
        self.model = self._create_model(event.new, replacement_params)
        self.model_selector_view = None

    def _message_output_setup(self):
        async def pack(message_payload: MessagePayload) -> MessagePayload:
            return message_payload

        self.ports.add_output(name='message_output', pack_payload_callback=pack)

    def _messages_emit_input_setup(self):
        async def unpack(payload: Union[MessagePayload, List[Union[MessagePayload, ToolsResponsePayload]]]):
            """
            Handle incoming payloads which may be a single message or a list of messages.
            
            Args:
                payload: Single message payload or a list of message/tool response payloads
                        (typically from history handler)
            """
            # Convert to list if it's a single payload
            if not isinstance(payload, list):
                payloads = [payload]
            else:
                # It's already a list
                payloads = payload

            # Directly generate and emit response from all incoming payloads
            response = self.model.generate_response(payloads)
            if self.generate_content_on_emit:
                # Populate the message content before emitting
                await response.model.aget_message()
            await self.ports.output['message_output'].stage_emit(message_payload=response)

        self.ports.add_input(
            name='messages_emit_input',
            unpack_payload_callback=unpack,
            payload_type=Union[MessagePayload, List[Union[MessagePayload, ToolsResponsePayload]]]
        )

    def _tools_input_setup(self):
        async def unpack(payload: StructuredPayload):
            self.model.tools = payload.model.data

        self.ports.add_input(
            name='tools_input',
            unpack_payload_callback=unpack,
            payload_type=StructuredPayload
        )

    @Component.view
    def create_model_selector_view(
        self,
        models: Optional[Union[list[Union[str, dict]], dict]] = None,
        show_provider_selector: bool = True,
        provider: str = 'OpenAI',
        model: Union[str, dict] = 'openai/gpt-4o-mini',
        orientation: Literal['vertical', 'horizontal'] = 'horizontal',
        model_selector_width: int = None,
        provider_selector_width: int = None,
        selector_css: list[str] = [],
        height: int = 57
    ) -> pn.widgets.Select | pn.Column | pn.Row:
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
            else:
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
        provider_model_map = self.model.get_provider_model_catalog(models=models, max_providers=6)
        provider_options = {
            self.model.provider_display_name(provider_key): provider_key
            for provider_key in provider_model_map.keys()
        }
        if not provider_options:
            provider_options = {'Default': 'default'}
            provider_model_map = {'default': []}

        normalized_default_model = self.model.normalize_model_name(model) if isinstance(model, str) else None
        default_provider_key = self.model.provider_key_for_label(provider)
        if normalized_default_model and '/' in normalized_default_model:
            default_provider_key = normalized_default_model.split('/', 1)[0].lower()
        if default_provider_key not in provider_model_map:
            default_provider_key = next(iter(provider_model_map.keys()))

        def build_model_options(provider_key: str) -> dict:
            return process_models(provider_model_map.get(provider_key, []))

        model_selector = pn.widgets.Select(
            name='Model Selector',
            options=build_model_options(default_provider_key),
            stylesheets=selector_css,
            width=model_selector_width,
            sizing_mode='stretch_width',
            margin=0
        )

        def select_default_model(options: dict, preferred_model: Optional[str]) -> Optional[dict]:
            if preferred_model and preferred_model in options:
                return options[preferred_model]
            if isinstance(model, dict):
                for cfg in options.values():
                    if cfg == model:
                        return cfg
            if options:
                return next(iter(options.values()))
            return None

        default_config = select_default_model(model_selector.options, normalized_default_model)
        if default_config is not None:
            model_selector.value = default_config
            self.model.model_name = default_config["model"]
            if hasattr(self.model, 'base_url'):
                self.model.base_url = default_config["base_url"]

        def on_model_change(event):
            self.model.model_name = event.new["model"]
            if hasattr(self.model, 'base_url'):
                self.model.base_url = event.new["base_url"]

        model_selector.param.watch(on_model_change, 'value')

        if not show_provider_selector:
            return pn.Row(model_selector)

        provider_selector = pn.widgets.Select(
            name='Provider Selector',
            value=default_provider_key,
            options=provider_options,
            stylesheets=selector_css,
            width=provider_selector_width,
            sizing_mode='stretch_width',
            margin=0
        )

        def on_provider_change(event):
            new_options = build_model_options(event.new)
            model_selector.options = new_options
            default_cfg = select_default_model(new_options, normalized_default_model if event.new == default_provider_key else None)
            if default_cfg is not None:
                model_selector.value = default_cfg
                self.model.model_name = default_cfg["model"]
                if hasattr(self.model, 'base_url'):
                    self.model.base_url = default_cfg["base_url"]

        provider_selector.param.watch(on_provider_change, 'value')

        if orientation == 'vertical':
            self.model_selector_view = pn.Column(provider_selector, model_selector)
        else:
            self.model_selector_view = pn.Row(provider_selector, pn.Spacer(width=10), model_selector)
        return self.model_selector_view