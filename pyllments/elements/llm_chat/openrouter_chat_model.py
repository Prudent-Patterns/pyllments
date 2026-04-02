import os

import param
from openrouter import OpenRouter
from dotenv import load_dotenv

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class OpenRouterChatModel(Model):
    """Chat model implementation backed by the OpenRouter Python SDK."""

    model_name = param.String(default='openai/gpt-4o-mini', doc='OpenRouter model name')

    model_args = param.Dict(default={}, doc="""
        Additional arguments to pass to the OpenRouter chat request""")

    output_mode = param.Selector(
        objects=['atomic', 'stream'],
        default='stream',
        doc="Whether to stream the response or return it all at once")

    response_format = param.Parameter(default=None, doc="""
        Response format to pass to the model. Pydantic model or dictionary definition""")

    functions = param.Dict(default=None, doc="""
        Reserved for compatibility. OpenRouter uses `tools` for function-style calls.""")

    tools = param.List(default=None, doc="List of tools for function calling")

    api_key = param.String(default=None, allow_None=True, doc="""
        OpenRouter API key. Falls back to OPENROUTER_API_KEY when not provided.""")

    client_args = param.Dict(default={}, doc="""
        Additional keyword arguments passed to OpenRouter client construction.""")

    MAJOR_PROVIDER_KEYS = ['openai', 'anthropic', 'google', 'x-ai', 'mistralai', 'meta-llama']
    PROVIDER_KEY_TO_LABEL = {
        'openai': 'OpenAI',
        'anthropic': 'Anthropic',
        'google': 'Google',
        'x-ai': 'xAI',
        'xai': 'xAI',
        'mistralai': 'Mistral',
        'meta-llama': 'Meta',
    }
    FALLBACK_MODEL_IDS = [
        'openai/gpt-4o-mini',
        'openai/gpt-4.1-mini',
        'anthropic/claude-3.7-sonnet',
        'google/gemini-2.5-pro',
        'x-ai/grok-3-mini',
        'mistralai/mistral-small-3.1-24b-instruct',
    ]

    def _messages_to_openrouter(self, messages: list[MessagePayload]) -> list[dict[str, str]]:
        """Convert MessagePayload instances to OpenRouter chat message dictionaries."""
        return [
            {
                'role': msg.model.role,
                'content': msg.model.content
            }
            for msg in messages
        ]

    @classmethod
    def normalize_model_name(cls, model_name: str) -> str:
        """Normalize optional `openrouter/` prefix to provider/model format."""
        if model_name.startswith('openrouter/'):
            return model_name.split('openrouter/', 1)[1]
        return model_name

    @classmethod
    def get_provider_model_catalog(
        cls,
        models: dict | list | None = None,
        max_providers: int = 6,
    ) -> dict[str, list[str]]:
        """
        Return a curated OpenRouter provider->models catalog for selector rendering.
        """
        provider_map: dict[str, list[str]] = {}

        def add_model(model_name: str):
            normalized_model_name = cls.normalize_model_name(model_name)
            if '/' not in normalized_model_name:
                return
            provider_key = normalized_model_name.split('/', 1)[0].lower()
            provider_map.setdefault(provider_key, [])
            if normalized_model_name not in provider_map[provider_key]:
                provider_map[provider_key].append(normalized_model_name)

        if not models:
            for model_name in cls._fetch_available_model_ids():
                add_model(model_name)
        elif isinstance(models, dict):
            values_are_collections = any(isinstance(value, (list, tuple)) for value in models.values())
            if values_are_collections:
                for provider_models in models.values():
                    if isinstance(provider_models, (list, tuple)):
                        for model_item in provider_models:
                            if isinstance(model_item, dict):
                                model_val = model_item.get("model") or model_item.get("name")
                                if model_val:
                                    add_model(model_val)
                            else:
                                add_model(str(model_item))
                    else:
                        add_model(str(provider_models))
            else:
                for value in models.values():
                    if isinstance(value, dict):
                        model_val = value.get("model") or value.get("name")
                        if model_val:
                            add_model(model_val)
                    else:
                        add_model(str(value))
        else:
            for model_item in models:
                if isinstance(model_item, dict):
                    model_val = model_item.get("model") or model_item.get("name")
                    if model_val:
                        add_model(model_val)
                else:
                    add_model(str(model_item))

        filtered_map: dict[str, list[str]] = {}
        for provider_key in cls.MAJOR_PROVIDER_KEYS:
            if provider_key in provider_map:
                filtered_map[provider_key] = provider_map[provider_key]

        if not filtered_map:
            for provider_key in sorted(provider_map.keys())[:max_providers]:
                filtered_map[provider_key] = provider_map[provider_key]

        return filtered_map

    @classmethod
    def _fetch_available_model_ids(cls) -> list[str]:
        """
        Fetch model ids using the OpenRouter Python SDK.

        Falls back to a small built-in set when SDK model listing is unavailable
        so the selector remains usable.
        """
        try:
            load_dotenv(override=False)
            api_key = os.getenv('OPENROUTER_API_KEY')
            client_kwargs = {'api_key': api_key} if api_key else {}
            with OpenRouter(**client_kwargs) as client:
                response = client.models.list()
            return [
                str(model_data.id)
                for model_data in getattr(response, 'data', [])
                if getattr(model_data, 'id', None)
            ] or list(cls.FALLBACK_MODEL_IDS)
        except Exception:
            return list(cls.FALLBACK_MODEL_IDS)

    @classmethod
    def provider_display_name(cls, provider_key: str) -> str:
        """Return UI-friendly provider label from provider key."""
        return cls.PROVIDER_KEY_TO_LABEL.get(provider_key.lower(), provider_key.title())

    @classmethod
    def provider_key_for_label(cls, provider_label: str) -> str:
        """Map UI provider label to provider key."""
        normalized = provider_label.lower()
        reverse = {value.lower(): key for key, value in cls.PROVIDER_KEY_TO_LABEL.items()}
        return reverse.get(normalized, normalized)

    def _build_client_kwargs(self) -> dict:
        # Ensure OPENROUTER_API_KEY from a local .env is discoverable at runtime.
        load_dotenv(override=False)
        client_kwargs = dict(self.client_args)
        api_key = self.api_key or os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            raise ValueError(
                "Missing OpenRouter credentials. Set OPENROUTER_API_KEY in the "
                "environment or .env (for recipes, pass --env .env), or pass "
                "api_key directly to LLMChatElement."
            )
        client_kwargs['api_key'] = api_key
        return client_kwargs

    def _build_request_kwargs(self, messages: list[MessagePayload], stream: bool) -> dict:
        request_kwargs = dict(self.model_args)
        request_kwargs.update({
            'model': self.model_name,
            'messages': self._messages_to_openrouter(messages),
            'stream': stream,
        })
        if self.response_format is not None:
            request_kwargs['response_format'] = self.response_format
        if self.tools:
            request_kwargs['tools'] = self.tools
        return request_kwargs

    async def _atomic_response(self, request_kwargs: dict):
        """Send a non-streaming request and return the OpenRouter response object."""
        async with OpenRouter(**self._build_client_kwargs()) as client:
            return await client.chat.send_async(**request_kwargs)

    async def _stream_events(self, request_kwargs: dict):
        """
        Yield streaming OpenRouter events while keeping the client context open.

        This keeps stream lifecycle ownership local to the model so downstream
        message processing can consume an async iterator safely.
        """
        async with OpenRouter(**self._build_client_kwargs()) as client:
            stream = await client.chat.send_async(**request_kwargs)
            async for event in stream:
                yield event

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """Generate a response through OpenRouter and package it into MessagePayload."""
        if self.output_mode == 'atomic':
            request_kwargs = self._build_request_kwargs(messages=messages, stream=False)
            return MessagePayload(
                role='assistant',
                message_coroutine=self._atomic_response(request_kwargs),
                mode='atomic'
            )
        if self.output_mode == 'stream':
            request_kwargs = self._build_request_kwargs(messages=messages, stream=True)
            return MessagePayload(
                role='assistant',
                message_coroutine=self._stream_events(request_kwargs),
                mode='stream'
            )
        raise ValueError(f"Invalid output mode: {self.output_mode}")
