import litellm
import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class LiteLLMChatModel(Model):
    """Chat model implementation backed by LiteLLM."""

    model_name = param.String(default='gpt-4o-mini', doc='Name of the model')

    model_args = param.Dict(default={}, doc="""
        Additional arguments to pass to the model""")

    output_mode = param.Selector(
        objects=['atomic', 'stream'],
        default='stream',
        doc="Whether to stream the response or return it all at once")

    base_url = param.String(doc="Base URL for the model", allow_None=True)

    response_format = param.Parameter(default=None, doc="""
        Response format to pass to the model. Pydantic model or dictionary definition""")

    functions = param.Dict(default=None, doc="""
        Functions to pass to the model. Dictionary of function definitions""")

    tools = param.List(default=None, doc="List of tools for function calling")

    PROVIDER_LABEL_TO_KEY = {
        'OpenAI': 'openai',
        'Anthropic': 'anthropic',
        'Gemini': 'gemini',
        'xAI': 'xai',
        'Groq': 'groq',
        'Mistral': 'mistral',
        'OpenRouter': 'openrouter',
        'Custom': 'custom',
    }
    PROVIDER_KEY_TO_LABEL = {value: key for key, value in PROVIDER_LABEL_TO_KEY.items()}

    def __init__(self, **params):
        super().__init__(**params)
        if self.base_url:
            self.model_args['base_url'] = self.base_url
        self.param.watch(self._update_base_url, 'base_url')

    def _update_base_url(self, event):
        self.model_args['base_url'] = self.base_url

    def _messages_to_litellm(self, messages: list[MessagePayload]) -> list[dict[str, str]]:
        """Convert MessagePayload instances to LiteLLM chat message dictionaries."""
        return [
            {
                'role': msg.model.role,
                'content': msg.model.content
            }
            for msg in messages
        ]

    @classmethod
    def get_provider_model_catalog(
        cls,
        models: dict | list | None = None,
        max_providers: int = 6,
    ) -> dict[str, list[str]]:
        """
        Return a provider-keyed model catalog for selector rendering.

        Parameters
        ----------
        models : dict | list | None
            Optional custom models to expose under the `custom` provider key.
        """
        provider_map = {
            'openai': litellm.open_ai_chat_completion_models,
            'anthropic': litellm.anthropic_models,
            'gemini': litellm.gemini_models,
            'xai': litellm.xai_models,
            'groq': litellm.groq_models,
            'mistral': litellm.mistral_chat_models,
            'openrouter': litellm.openrouter_models,
        }
        if models:
            custom_models: list[str] = []
            if isinstance(models, dict):
                for value in models.values():
                    if isinstance(value, dict):
                        model_val = value.get("model") or value.get("name")
                        if model_val:
                            custom_models.append(model_val)
                    else:
                        custom_models.append(str(value))
            else:
                for item in models:
                    if isinstance(item, dict):
                        model_val = item.get("model") or item.get("name")
                        if model_val:
                            custom_models.append(model_val)
                    else:
                        custom_models.append(str(item))
            if custom_models:
                provider_map['custom'] = custom_models
        return provider_map

    @classmethod
    def provider_display_name(cls, provider_key: str) -> str:
        """Return UI-friendly provider label from provider key."""
        return cls.PROVIDER_KEY_TO_LABEL.get(provider_key, provider_key.title())

    @classmethod
    def provider_key_for_label(cls, provider_label: str) -> str:
        """Map UI provider label to provider key."""
        return cls.PROVIDER_LABEL_TO_KEY.get(provider_label, provider_label.lower())

    @classmethod
    def normalize_model_name(cls, model_name: str) -> str:
        """Normalize model names for selector matching."""
        return model_name

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """
        Generate a response through LiteLLM.

        For atomic mode, this returns a MessagePayload that stores a coroutine.
        For stream mode, this returns a MessagePayload that stores a stream source.
        """
        litellm_messages = self._messages_to_litellm(messages)
        request_kwargs = dict(self.model_args)
        if self.tools:
            request_kwargs['tools'] = self.tools
        if self.functions:
            request_kwargs['functions'] = self.functions

        if self.output_mode == 'atomic':
            async def atomic_response():
                response = await litellm.acompletion(
                    model=self.model_name,
                    messages=litellm_messages,
                    response_format=self.response_format,
                    **request_kwargs
                )
                return response

            return MessagePayload(
                role='assistant',
                message_coroutine=atomic_response(),
                mode='atomic'
            )
        elif self.output_mode == 'stream':
            response_stream = litellm.acompletion(
                model=self.model_name,
                messages=litellm_messages,
                response_format=self.response_format,
                stream=True,
                **request_kwargs
            )
            return MessagePayload(
                role='assistant',
                message_coroutine=response_stream,
                mode='stream'
            )
        else:
            raise ValueError(f"Invalid output mode: {self.output_mode}")
