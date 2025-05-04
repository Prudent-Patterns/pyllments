"""Sets up a discord bot that can chat with a user via direct messages."""
from dataclasses import dataclass, field

from pyllments.elements import DiscordElement, LLMChatElement, HistoryHandlerElement, ContextBuilderElement


@dataclass
class Config:
    """Choose the model to use for chatting with the discord bot"""
    model_name: str = field(
        default='gpt-4o-mini',
        metadata={'help': 'The name of the model to use for the LLM chat.'})
    model_base_url: str = field(
        default=None,
        metadata={'help': 'The base URL of the model to use for the LLM chat.'})
    system_prompt: str = field(
        default=None,
        metadata={'help': 'The system prompt to use for the chat bot.'})

discord_el = DiscordElement()

llm_chat_el = LLMChatElement(
    model_name=config.model_name,
    base_url=config.model_base_url,
    output_mode='atomic'
    )

history_handler_el = HistoryHandlerElement(context_token_limit=12000)

# Set up ContextBuilder to aggregate history and new Discord messages
input_map = {
    'history': {'ports': [history_handler_el.ports.message_history_output], 'persist': True},
    'user_query': {'ports': [discord_el.ports.message_output]}
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

# Mirror chat recipe: route Discord messages silently into history, and LLM responses to emit history
discord_el.ports.message_output > history_handler_el.ports.messages_input
llm_chat_el.ports.message_output > history_handler_el.ports.message_emit_input

llm_chat_el.ports.message_output > discord_el.ports.message_input