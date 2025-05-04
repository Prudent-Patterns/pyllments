"""
A simple chat recipe with history handling and model selection.
"""
from dataclasses import dataclass, field

import panel as pn
from pyllments import flow
from pyllments.elements import (
    ChatInterfaceElement,
    LLMChatElement,
    HistoryHandlerElement,
    ContextBuilderElement
)


@dataclass
class Config:
    """
    Control the display parameters and models to be used.
    """
    height: int = field(
        default=800,
        metadata={
            "help": "Height of the chat interface in pixels."
        }
    )
    width: int = field(
        default=800,
        metadata={
            "help": "Overall width of the chat interface in pixels."
        }
    )
    history_token_limit: int = field(
        default=5000,
        metadata={
            "help": "Number of tokens to keep in the history at any given time."
        }
    )
    custom_models: dict = field(
        default_factory=dict,
        metadata={
            "help": """The custom models you wish to add to the model selector. Will be visible in the Provider dropdown.
            The format is a dictionary with the keys as the model display names. (On a single line - Use single quotes)
            '{"LOCAL DEEPSEEK": {"name": "ollama_chat/deepseek-r1:14b", "base_url": "http://172.17.0.3:11434"}, "OpenAI GPT-4o-mini": {"name": "gpt4o-mini"}}'
            """
        }
    )
    default_model: str = field(
        default='gpt-4o-mini',
        metadata={
            "help": "The default model to use when loading the interface."
        }
    )
    system_prompt: str = field(
        default=None,
        metadata={
            "help": "The system prompt to use when loading the interface."
        }
    )
    
    
chat_interface_el = ChatInterfaceElement()
llm_chat_el = LLMChatElement()
history_handler_el = HistoryHandlerElement(
    history_token_limit=config.history_token_limit,  # type: ignore
    tokenizer_model='gpt-4o'
)

input_map = {
    'history': {'ports': [history_handler_el.ports.message_history_output]},
    'user_query': {'ports': [chat_interface_el.ports.user_message_output]},
}
emit_order = ['[history]', 'user_query']

if config.system_prompt:
    sys_prompt_mapping = {
        'system_prompt_constant': {
            'role': 'system',
            'message': config.system_prompt
            }
    } 
    input_map = {**sys_prompt_mapping, **input_map}
    emit_order.insert(0, 'system_prompt_constant')


context_builder = ContextBuilderElement(
    input_map=input_map,
    emit_order=emit_order,
    outgoing_input_ports=[llm_chat_el.ports.messages_emit_input]
    )

# Route user messages into history only after chat interface processing
chat_interface_el.ports.user_message_output > history_handler_el.ports.message_emit_input

# Connect LLM output into chat interface for display
llm_chat_el.ports.message_output > chat_interface_el.ports.assistant_message_emit_input

# Route assistant messages into history only after chat interface display
chat_interface_el.ports.assistant_message_output > history_handler_el.ports.message_emit_input

@flow
def my_flow():
    interface_view = chat_interface_el.create_interface_view(width=config.width, height=config.height) # type: ignore
    model_selector_view = llm_chat_el.create_model_selector_view(models=config.custom_models, model=config.default_model) # type: ignore
    # Add the history view to display past messages
    # history_view = history_handler_el.create_context_view()

    main_view = pn.Column(
        model_selector_view,
        # history_view,
        pn.Spacer(height=10),
        interface_view,
        styles={'width': 'fit-content'}
    )
    return main_view