from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    StructuredRouterTransformer,
    MCPElement,
    HistoryHandlerElement,
    LLMChatElement,
)

chat_interface_el = ChatInterfaceElement()

context_builder_el = ContextBuilderElement(
    input_map={
        'user_message': {
            'ports': [chat_interface_el.ports.output['message_output']],
        }
    }
)