"""Sets up a discord bot that can chat with a user via direct messages."""
from dataclasses import dataclass, field

from pyllments.elements import DiscordElement, LLMChatElement, HistoryHandlerElement, ContextBuilderElement


@dataclass
class Config:
    """Choose the model to use for chatting with the discord bot"""
    bot_token: str = field(
        default=None,
        metadata={'help': 'The token for the discord bot. Not necessary if DISCORD_BOT_TOKEN env var present.'}
    )
    model_name: str = field(
        default='gpt-4o-mini',
        metadata={'help': 'The name of the model to use for the LLM chat.'})
    model_base_url: str = field(
        default=None,
        metadata={'help': 'The base URL of the model to use for the LLM chat.'})
    system_prompt: str = field(
        default=None,
        metadata={'help': 'The system prompt to use for the chat bot.'})

discord_el = DiscordElement(bot_token=config.bot_token)

llm_chat_el = LLMChatElement(
    model_name=config.model_name,
    base_url=config.model_base_url,
    output_mode='atomic'
    )

history_handler_el = HistoryHandlerElement(context_token_limit=12000)

# Set up ContextBuilder to aggregate history and new Discord messages
input_map = {
    'history': {'ports': [history_handler_el.ports.message_history_output], 'persist': True},
    'user_query': {'ports': [discord_el.ports.user_message_output]}
}
emit_order = ['[history]', 'user_query']

if config.system_prompt:
    input_map = {
        'system_prompt_constant': {'role': 'system', 'message': config.system_prompt},
        **input_map
    }
    emit_order.insert(0, 'system_prompt_constant')

context_builder = ContextBuilderElement(
    input_map=input_map,
    emit_order=emit_order,
    outgoing_input_ports=[llm_chat_el.ports.messages_emit_input]
)

# Hook user and assistant flows like the chat recipe
# Route incoming user messages into history
discord_el.ports.user_message_output > history_handler_el.ports.message_emit_input
# Send LLM responses to Discord then record them in history via unified emit port
llm_chat_el.ports.message_output > discord_el.ports.message_emit_input
discord_el.ports.assistant_message_output > history_handler_el.ports.message_emit_input