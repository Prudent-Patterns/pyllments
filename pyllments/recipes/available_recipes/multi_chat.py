"""
Creates a multi-chat interface where you can experiment with 4 different LLMs at once.
"""
from dataclasses import dataclass, field

import panel as pn
from pyllments.serve import flow
from pyllments.elements import ChatInterfaceElement, LLMChatElement


@dataclass
class Config:
    """
    Configuration parameters for the multi-chat interface.

    Attributes
    ----------
    width : int
        Main container width for the interface.
    height : int
        Main container height for the interface.
    custom_models : dict
        A dictionary of custom models to be used in the chat interface.
    """
    width: int = field(
        default=1200, metadata={"help": "Main container width"}
    )
    height: int = field(
        default=800, metadata={"help": "Main container height"}
    )
    custom_models: dict = field(
        default_factory=dict,
        metadata={
            "help": """
            The custom models you wish to add to the model selector. Will be visible in the Provider dropdown.
            The format is a dictionary with the keys as the model display names. (On a single line - Use single quotes)
            '{"LOCAL DEEPSEEK": {"name": "ollama_chat/deepseek-r1:14b", "base_url": "http://172.17.0.3:11434"}, "OpenAI GPT-4o-mini": {"name": "gpt4o-mini"}}'
            """
        }
    )

# CSS override to prevent chatfeed collapse when empty
chatfeed_height_fix = """
/*:host {
    min-height: 100px !important; /* Ensure minimum height to prevent collapse */
} */
"""

@flow
def create_gui():

    # Instantiate chat interface elements.
    chat_el0 = ChatInterfaceElement()
    chat_el1 = ChatInterfaceElement()
    chat_el2 = ChatInterfaceElement()
    chat_el3 = ChatInterfaceElement()

    # Instantiate LLM-based chat elements.
    llm_el0 = LLMChatElement()
    llm_el1 = LLMChatElement()
    llm_el2 = LLMChatElement()
    llm_el3 = LLMChatElement()
    
    # Connect multiple chat interfaces using dot notation.
    chat_el0.ports.message_output > chat_el1.ports.message_emit_input
    chat_el0.ports.message_output > chat_el2.ports.message_emit_input
    chat_el0.ports.message_output > chat_el3.ports.message_emit_input

    # Create bidirectional connections between each chat element and its corresponding LLM element.
    chat_el0.ports.message_output > llm_el0.ports.messages_emit_input
    llm_el0.ports.message_output > chat_el0.ports.message_input

    chat_el1.ports.message_output > llm_el1.ports.messages_emit_input
    llm_el1.ports.message_output > chat_el1.ports.message_input

    chat_el2.ports.message_output > llm_el2.ports.messages_emit_input
    llm_el2.ports.message_output > chat_el2.ports.message_input

    chat_el3.ports.message_output > llm_el3.ports.messages_emit_input
    llm_el3.ports.message_output > chat_el3.ports.message_input

    # Build the GUI layout leveraging the config parameters.
    chat_input_height = 150  # Height for the chat input row
    chatfeed_height = (config.height - (chat_input_height + 30)) // 2  # Adjusting for spacing and input height

    col1 = pn.Column(
        llm_el0.create_model_selector_view(models=config.custom_models),
        pn.Spacer(height=10),
        chat_el0.create_chatfeed_view(height=int(chatfeed_height), stylesheets=[chatfeed_height_fix]),
        pn.Spacer(height=10), 
        llm_el1.create_model_selector_view(models=config.custom_models),
        pn.Spacer(height=10),
        chat_el1.create_chatfeed_view(height=int(chatfeed_height), stylesheets=[chatfeed_height_fix])
    )
    col2 = pn.Column(
        llm_el2.create_model_selector_view(models=config.custom_models),
        pn.Spacer(height=10),
        chat_el2.create_chatfeed_view(height=int(chatfeed_height), stylesheets=[chatfeed_height_fix]),
        pn.Spacer(height=10),
        llm_el3.create_model_selector_view(models=config.custom_models),
        pn.Spacer(height=10),
        chat_el3.create_chatfeed_view(height=int(chatfeed_height), stylesheets=[chatfeed_height_fix])
    )
    main_col = pn.Column(
        pn.Row(
            pn.Row(col1,
                   pn.Spacer(width=10),
                   col2)
        ),
        pn.Spacer(height=10),
        chat_el0.create_chat_input_row_view(height=chat_input_height),
        width=config.width,
    )
    
    return main_col