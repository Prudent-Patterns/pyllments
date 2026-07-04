"""
Gateway-driven chat flow for production application integration.

Wire ``ChatGatewayElement`` into history and LLM elements, then drive the flow
from application code via :meth:`ChatGatewayElement.submit_message` rather than
a Panel UI or blocking HTTP response future.
"""
from dataclasses import dataclass, field

from pyllments.elements import ChatGatewayElement, HistoryHandlerElement, LLMChatElement


@dataclass
class Config:
    """Configuration for the gateway chat recipe."""

    history_token_limit: int = field(
        default=10000,
        metadata={
            "help": "Number of tokens to keep in the history at any given time."
        },
    )
    model_name: str = field(
        default='openai/gpt-4o-mini',
        metadata={
            "help": "OpenRouter/LiteLLM model name for the chat element."
        },
    )


gateway_el = ChatGatewayElement()
llm_chat_el = LLMChatElement(
    model_name=config.model_name,
    output_mode='stream',
    generate_content_on_emit=False,
)
history_handler_el = HistoryHandlerElement(history_token_limit=config.history_token_limit)

gateway_el.ports.message_output > history_handler_el.ports.payload_emit_input
history_handler_el.ports.context_output > llm_chat_el.ports.messages_emit_input
llm_chat_el.ports.message_output > gateway_el.ports.assistant_message_input
llm_chat_el.ports.message_output > history_handler_el.ports.payload_input
