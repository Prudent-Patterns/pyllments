"""
This recipe demonstrates how to create a basic chat flow served via an API endpoint.
"""
from dataclasses import dataclass, field

from pyllments.elements import ChatInterfaceElement, LLMChatElement, HistoryHandlerElement

from dataclasses import dataclass, field

from pyllments.elements import ChatInterfaceElement, LLMChatElement, APIElement
from pyllments import flow


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
    custom_models: dict = field(
        default_factory=dict,
        metadata={
            "help": "A dictionary of custom models to be used in the chat interface."
        }
    )
    

chat_interface_el = ChatInterfaceElement()
llm_chat_el = LLMChatElement()
history_handler_el = HistoryHandlerElement(history_token_limit=config.history_token_limit)
api_el = APIElement(
    endpoint='api',
    connected_input_map={
        'message_input': llm_chat_el.ports.output['message_output']
    },
    response_dict={
        'message_input': {
            'message': get_streamed_message,
            'role': 'role'
        }
    },
    request_output_fn=request_output_fn
)
