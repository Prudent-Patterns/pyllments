import litellm
import param

from pyllments.base.model_base import Model
from pyllments.payloads.message import MessagePayload


class LLMChatModel(Model):
    model_name = param.String(default='gpt-4o-mini', doc='Name of the model')
    
    model_args = param.Dict(default={}, doc="""
        Additional arguments to pass to the model""")
    
    output_mode = param.Selector(
        objects=['atomic', 'stream'],
        default='stream',
        doc="Whether to stream the response or return it all at once")
    
    base_url = param.String(doc="Base URL for the model", allow_None=True)

    response_format = param.Parameter(default=None, doc="Response format to pass to the model")

    def __init__(self, **params):
        super().__init__(**params)
        if self.base_url:
            self.model_args['base_url'] = self.base_url
        self.param.watch(self._update_base_url, 'base_url')

    def _update_base_url(self, event):
        self.model_args['base_url'] = self.base_url

    def _messages_to_litellm(self, messages: list[MessagePayload]) -> list[dict[str, str]]:
        """Convert MessagePayloads to LiteLLM format"""
        return [
            {
                'role': msg.model.role,
                'content': msg.model.content
            }
            for msg in messages
        ]

    def generate_response(self, messages: list[MessagePayload]) -> MessagePayload:
        """
        Generate a response using LiteLLM, ensuring that the current base_url is passed if provided.
        For atomic mode, wraps the call in a coroutine so that the response can be awaited elsewhere.
        """
        litellm_messages = self._messages_to_litellm(messages)

        if self.output_mode == 'atomic':
            # Wrap the atomic call in an async function so that a coroutine is stored.
            async def atomic_response():
                # Await the atomic completion from LiteLLM.
                response = await litellm.acompletion(
                    model=self.model_name,
                    messages=litellm_messages,
                    response_format=self.response_format,
                    **self.model_args
                )
                return response

            # The MessagePayload now holds a coroutine even for atomic mode.
            return MessagePayload(
                role='assistant',
                message_coroutine=atomic_response(),
                mode='atomic'
            )
        elif self.output_mode == 'stream':
            # For stream mode, the completion is expected to be a streaming coroutine.
            response_stream = litellm.acompletion(
                model=self.model_name,
                messages=litellm_messages,
                response_format=self.response_format,
                stream=True,
                **self.model_args
            )
            return MessagePayload(
                role='assistant',
                message_coroutine=response_stream,
                mode='stream'
            )
        else:
            raise ValueError(f"Invalid output mode: {self.output_mode}")