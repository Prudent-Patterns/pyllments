"""
This recipe demonstrates how to create a basic chat flow served via an API endpoint.
"""
from dataclasses import dataclass, field

from pyllments.elements import APIElement, HistoryHandlerElement, LLMChatElement
from pyllments.payloads import MessagePayload


@dataclass
class Config:
    """
    Control the api endpoint and number of tokens to keep in the history at any given time.
    """
    api_endpoint: str = field(
        default='api',
        metadata={
            "help": "Name of the API endpoint for external access. Must be URL-safe and unique."
        }
    )
    history_token_limit: int = field(
        default=10000,
        metadata={
            "help": "Number of tokens to keep in the history at any given time."
        }
    )
    model_name: str = field(
        default='gpt-4o-mini',
        metadata={
            "help": "The name of the model to use in the chat interface."
        }
    )
    

llm_chat_el = LLMChatElement(model_name=config.model_name, output_mode='atomic')
history_handler_el = HistoryHandlerElement(history_token_limit=config.history_token_limit)

history_handler_el.ports.messages_output > llm_chat_el.ports.messages_emit_input
llm_chat_el.ports.message_output > history_handler_el.ports.messages_input


def request_output_fn(message: str, role: str) -> MessagePayload:
    return MessagePayload(content=message, role=role)

api_el = APIElement(
    endpoint='api',
    connected_input_map={
        'message_input': llm_chat_el.ports.message_output
    },
    response_dict={
        'message_input': {
            'message': lambda payload: payload.model.aget_message(),
            'role': 'role'
        }
    },
    request_output_fn=request_output_fn
)

api_el.ports.api_output > history_handler_el.ports.message_emit_input
