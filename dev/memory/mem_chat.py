import panel as pn

from pyllments import flow
from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
    TextElement
)
from pyllments.payloads import MessagePayload

from mem_models import FactualMemory

LLM_NAME = 'gpt-4.1'

chat_el = ChatInterfaceElement()
history_el = HistoryHandlerElement(context_token_limit=3000)
chat_el.ports.user_message_output > history_el.ports.messages_input
chat_el.ports.assistant_message_output > history_el.ports.message_emit_input

main_context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': 'system',
            'message': "You are an elite assistant that can answer questions and help with tasks."
        },
        'query': {'ports': [chat_el.ports.user_message_output]},
        'history_constant': {
            'role': 'system',
            'message': "Below is a list of messages that makes up the conversation history so far.",
            'depends_on': 'history'
        },
        'history': {'ports': [history_el.ports.message_history_output]},
        'conversational_memory': {'payload_type': MessagePayload},
        'conversational_memory_template': {
            'role': 'system',
            'message': "Below is a set of running conversational summaries.\n"
                        "{{ conversational_memory }}"
        },
        'factual_memory': {'payload_type': MessagePayload},
        'factual_memory_template': {
            'role': 'system',
            'message': "Below is a set of factual memories gathered across your conversation so far.\n"
                        "{{ factual_memory }}"
        }   
    },
    emit_order=[
        'system_prompt_constant',
        '[history_constant]',
        '[history]',
        '[conversational_memory_template]',
        '[factual_memory_template]',
        'query'
    ]
)

main_llm_el = LLMChatElement(model_name=LLM_NAME)
main_context_builder_el.ports.messages_output > main_llm_el.ports.messages_emit_input
main_llm_el.ports.message_output > chat_el.ports.message_emit_input

# ================================
# Conversational Memory 
# ================================
conversational_context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': 'system',
            'message': "You are a memory module of a larger conversational system. "
                       "You are responsible for maintaining a running summary of the conversation so far. "
                       "You'll be outputting basic XML elements to demarcate the different types of summary."
                       "Use markdown triple backtickformatting surrounding the entire response so we can render it correctly."
                       "The elements which need to be included in every response are as follows -- they need to be between their respective tags like <contextual>something goes here</contextual>: \n"
                       "<contextual>: represents the main themes and the evolution of topics.\n"
                       "<emotional>: capture the overall mood and emotional shifts.\n"
                       "<tasks>: follows the progression of tasks and goals.\n"
                       "<social>: highlight the interpersonal dynamics and rapport."

        },
        'history_constant': {
            'role': 'system',
            'message': "Below is a list of messages that makes up the conversation history so far. \n"
                       "This will be used to build a running summary."
        },
        'history': {'ports': [history_el.ports.message_history_output]},
        'conversational_memory': {'payload_type': MessagePayload},
        'conversational_memory_template': {
            'role': 'system',
            'message': "Below is a set of running conversational summaries."
                       "Be sure to take these into account when building new ones in your response.\n"
                       "{{ conversational_memory }}"
        }
    },
    emit_order=[
        'system_prompt_constant',
        'history_constant',
        'history',
        '[conversational_memory_template]',
    ]
)

conversational_llm_el = LLMChatElement(model_name=LLM_NAME)
conversational_text_el = TextElement()
conversational_context_builder_el.ports.messages_output > \
    conversational_llm_el.ports.messages_emit_input
conversational_llm_el.ports.message_output > conversational_text_el.ports.message_input
conversational_text_el.ports.message_output > \
    conversational_context_builder_el.ports.conversational_memory
conversational_text_el.ports.message_output > \
    main_context_builder_el.ports.conversational_memory

# ================================
# Factual Memory 
# ================================
factual_context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': 'system',
            'message': "You are a memory module of a larger conversational system."
                       "You are responsible for maintaining a running summary of the conversation so far."
                       "You'll be outputting JSON to keep track of certain facts that are relevant to the conversation."
        },
        'history_constant': {
            'role': 'system',
            'message': "Below is a list of messages that makes up the conversation history so far.",
        },
        'history': {'ports': [history_el.ports.message_history_output]},
        'factual_memory': {'payload_type': MessagePayload},
        'factual_memory_template': {
            'role': 'system',
            'message': "Below is a set of factual memories gathered across your conversation so far. You will update or add to these facts as you go.\n"
                        "{{ factual_memory }}"
        }
    },
    emit_order=[
        'system_prompt_constant',
        'history_constant',
        'history',
        '[factual_memory_template]'
    ]
)

factual_llm_el = LLMChatElement(model_name=LLM_NAME, response_format=FactualMemory)
factual_text_el = TextElement()
factual_context_builder_el.ports.messages_output > \
    factual_llm_el.ports.messages_emit_input
factual_llm_el.ports.message_output > factual_text_el.ports.message_input
factual_text_el.ports.message_output > \
    factual_context_builder_el.ports.factual_memory
factual_text_el.ports.message_output > \
    main_context_builder_el.ports.factual_memory

@flow
def main():
    return pn.Row(
        chat_el.create_interface_view(width=500, height=800),
        pn.Spacer(width=10),
        conversational_text_el.create_display_view(width=500, height=800, title="Conversational Memory"),
        pn.Spacer(width=10),
        factual_text_el.create_display_view(width=500, height=800, title="Factual Memory")
    )