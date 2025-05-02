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

# Add ContextBuilder if system prompt is provided
if config.system_prompt:
    from pyllments.elements import ContextBuilderElement
    context_builder = ContextBuilderElement(
        input_map={
            'system_prompt_constant': {
                'role': 'system',
                'message': config.system_prompt
            },
            'history': {
                'role': 'user',
                'payload_type': list[MessagePayload],
                'ports': [history_handler_el.ports.message_history_output],
                'persist': True
            }
        },
        trigger_map={
            'history': ['system_prompt_constant', 'history']
        }
    )
    context_builder.ports.messages_output > llm_chat_el.ports.messages_emit_input
else:
    history_handler_el.ports.messages_output > llm_chat_el.ports.messages_emit_input

discord_el.ports.message_output > history_handler_el.ports.message_emit_input
llm_chat_el.ports.message_output > history_handler_el.ports.messages_input
llm_chat_el.ports.message_output > discord_el.ports.message_input