"""
A simple example of a chat interface with an API endpoint.
This recipe demonstrates how to create a basic chat interface with an LLM backend
and expose it through an API endpoint.
"""
from dataclasses import dataclass, field

from pyllments.elements import ChatInterfaceElement, LLMChatElement, APIElement
from pyllments.payloads import MessagePayload
from pyllments import flow


@dataclass
class Config:
    """
    Control the display parameters and api endpoint for the simple flow recipe.
    """
    feed_height: int = field(
        default=700,
        metadata={
            "help": "Height of the chat message feed in pixels. Larger values show more message history.",
            "min": 200,
            "max": 2000
        }
    )
    input_height: int = field(
        default=120,
        metadata={
            "help": "Height of the input text box in pixels. Larger values provide more space for composing messages.",
            "min": 50,
            "max": 500
        }
    )
    width: int = field(
        default=800,
        metadata={
            "help": "Overall width of the chat interface in pixels. Adjust based on your display needs.",
            "min": 400,
            "max": 2000
        }
    )
    api_endpoint: str = field(
        default='api',
        metadata={
            "help": "Name of the API endpoint for external access. Must be URL-safe and unique."
        }
    )


# Initialize elements with config
chat_interface_el = ChatInterfaceElement()
llm_chat_el = LLMChatElement()

def request_output_fn(message: str, role: str) -> MessagePayload:
    # Removed Langchain-specific messaging; directly pass the message as content.
    return MessagePayload(content=message, role=role)

async def get_streamed_message(payload):
    return await payload.model.streamed_message()

api_el = APIElement(
    endpoint=config['api_endpoint'],  # Using the endpoint defined in the configuration.
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

# Connect elements
chat_interface_el.ports.output['message_output'] > llm_chat_el.ports.input['messages_input']
llm_chat_el.ports.output['message_output'] > chat_interface_el.ports.input['message_input']
api_el.ports.output['api_output'] > chat_interface_el.ports.input['message_emit_input']


@flow
def create_pyllments_flow():
    """Create the Pyllments flow with a chat interface and API endpoint.
    
    Returns
    -------
    panel.Column
        The Panel interface for the chat application
    """
    return chat_interface_el.create_interface_view(
        feed_height=config.feed_height,
        input_height=config.input_height,
        width=config.width
    )