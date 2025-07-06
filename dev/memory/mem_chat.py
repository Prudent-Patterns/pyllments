from pyllments import flow
from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    HistoryHandlerElement,
    LLMChatElement,
    TextElement
)
from pyllments.payloads import MessagePayload

chat_el = ChatInterfaceElement()
history_el = HistoryHandlerElement(context_token_limit=3000)
chat_el.ports.user_message_output > history_el.ports.messages_input
chat_el.ports.assistant_message_output > history_el.ports.messages_emit_input

main_context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': 'system',
            'message': "You are an elite assistant that can answer questions and help with tasks."
        },
        'query': {'ports': [chat_el.ports.message_input]},
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

main_llm_el = LLMChatElement(model_name='gpt-4.1')
main_context_builder_el.ports.messages_output > main_llm_el.ports.messages_emit_input

# ================================
# Conversational Memory 
# ================================
conversational_context_builder_el = ContextBuilderElement(
    input_map={
        'system_prompt_constant': {
            'role': 'system',
            'message': "You are a memory module of a larger conversational system."
                       "You are responsible for maintaining a running summary of the conversation so far."
                       "You'll be outputting basic XML to demarcate the different types of summary."
                       ""
        },
        'history_constant': {
            'role': 'system',
            'message': "Below is a list of messages that makes up the conversation history so far.",
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
        '[conversational_memory_template]',
    ]
)

conversational_llm_el = LLMChatElement(model_name='gpt-4.1')
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
                       ""
        }
    }
)