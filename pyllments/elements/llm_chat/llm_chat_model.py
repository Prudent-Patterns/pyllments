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

    def __init__(self, **params):
        super().__init__(**params)

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
        """Generate a response using LiteLLM"""
        litellm_messages = self._messages_to_litellm(messages)
        
        if self.output_mode == 'atomic':
            response = litellm.acompletion(
                model=self.model_name,
                messages=litellm_messages,
                **self.model_args
            )
            return MessagePayload(
                role='assistant',
                message_coroutine=response,
                mode='atomic'
            )
            
        elif self.output_mode == 'stream':
            response_stream = litellm.acompletion(
                model=self.model_name,
                messages=litellm_messages,
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