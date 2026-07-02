"""
App-integration scratchpad for a basic chat harness.

Uses ChatInterfaceElement as the interactive boundary today. The wiring is kept
close to a future ChatGatewayElement substitution:

    ChatInterface.user_message_output  ->  ChatGateway.message_output
    LLM.message_output                 ->  ChatGateway.assistant_message_input
    TurnHandle                         ->  host-app stream/final-message API
"""
import panel as pn

from pyllments import flow
from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
)

SYSTEM_PROMPT = (
    "You are a helpful assistant embedded in an application. "
    "Answer clearly and concisely."
)

chat_interface_el = ChatInterfaceElement()
history_handler_el = HistoryHandlerElement(
    history_token_limit=8000,
    context_token_limit=4000,
    tokenizer_model="gpt-4o",
)
llm_chat_el = LLMChatElement(
    model_name="openai/gpt-4o-mini",
    output_mode="stream",
    generate_content_on_emit=False,
)

context_builder_el = ContextBuilderElement(
    input_map={
        "system_prompt_constant": {
            "role": "system",
            "message": SYSTEM_PROMPT,
        },
        "history": {"ports": [history_handler_el.ports.context_output]},
        "user_query": {"ports": [chat_interface_el.ports.user_message_output]},
    },
    trigger_map={
        "user_query": [
            "system_prompt_constant",
            "[history]",
            "user_query",
        ],
    },
    outgoing_input_ports=[llm_chat_el.ports.messages_emit_input],
)

# User turn: emit prior history context, then record the new user message.
chat_interface_el.ports.user_message_output > history_handler_el.ports.payload_pre_emit_input
history_handler_el.ports.context_output > context_builder_el.ports.history

# Assistant turn: chat interface consumes the stream first, then history stores the ready payload.
llm_chat_el.ports.message_output > chat_interface_el.ports.message_emit_input
llm_chat_el.ports.message_output > history_handler_el.ports.payload_input


@flow
def basic_chat_flow():
    interface_view = chat_interface_el.create_interface_view(input_height=120)
    model_selector_view = llm_chat_el.create_model_selector_view()
    history_view = history_handler_el.create_context_view()

    return pn.Row(
        pn.Column(
            model_selector_view,
            pn.Spacer(height=10),
            interface_view,
        ),
        pn.Spacer(width=12),
        history_view,
        sizing_mode="stretch_width",
    )
