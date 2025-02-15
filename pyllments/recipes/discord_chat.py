"""Sets up a discord bot that can chat with a user via direct messages."""
from dataclasses import dataclass, field

from pyllments.elements import DiscordElement, LLMChatElement, HistoryHandlerElement


@dataclass
class Config:
    """Choose the model to use for chatting with the discord bot"""
    model_name: str = field(
        default='gpt-4o-mini',
        metadata={'help': 'The name of the model to use for the LLM chat.'})
    model_base_url: str = field(
        default=None,
        metadata={'help': 'The base URL of the model to use for the LLM chat.'})

discord_el = DiscordElement()

llm_chat_el = LLMChatElement(
    model_name=config.model_name,
    model_base_url=config.model_base_url,
    output_mode='atomic'
    )

history_handler_el = HistoryHandlerElement(context_token_limit=12000)

discord_el.ports.message_output > history_handler_el.ports.message_emit_input
history_handler_el.ports.messages_output > llm_chat_el.ports.messages_emit_input
llm_chat_el.ports.message_output > history_handler_el.ports.messages_input
llm_chat_el.ports.message_output > discord_el.ports.message_input