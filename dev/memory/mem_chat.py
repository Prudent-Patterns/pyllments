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
        'query'
    ]
)

main_llm_el = LLMChatElement(model_name='gpt-4.1')
main_context_builder_el.ports.messages_output > main_llm_el.ports.messages_emit_input
