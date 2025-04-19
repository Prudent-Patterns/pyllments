from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    StructuredRouterTransformer,
    MCPElement,
    HistoryHandlerElement,
    LLMChatElement,
    PipeElement
)
from pyllments.payloads import MessagePayload, SchemaPayload, StructuredPayload
from pyllments.serve import flow

initial_context_pipe_el = PipeElement(receive_callback=lambda ps: f"Initial context pipe received: {ps}")

reply_pipe_el = PipeElement(receive_callback=lambda p: f"Reply pipe received: {p}")
tools_pipe_el = PipeElement(receive_callback=lambda p: f"Tools pipe received: {p}")
initial_llm_pipe_el = PipeElement(receive_callback=lambda p: f"LLM output content: {p.model.content}")

chat_interface_el = ChatInterfaceElement()

initial_context_builder_el = ContextBuilderElement(
    input_map={
        'main_system_message_constant': {
            'role': 'system',
            'message': "Your goal is to reply to the user in the best way possible using the tools you have access to. "
                       "You MUST reply ONLY in a valid JSON format in plain text without any code block notation or triple quotes that strictly complies with the JSON schema provided to you. "
                       "Do not include any text outside of the JSON. "
                       "One of the options will be to choose replying to the user without tools, or responding with "
                       "tools and parameters which will return their values to you in a future message that you'll "
                       "be able to respond to and synthesize information from. You will also be provided with a history "
                       "of our previous interactions if it is available."
        },
        'history_system_message_constant': {
            'role': 'system',
            'message': "The following is a history of our previous interactions between us",
            'depends_on': 'history'
        },
        'history': {
            'payload_type': list[MessagePayload],
        },
        'user_query_system_message_constant': {
            'role': 'system',
            'message': "The following is the user's query to you."
        },
        'user_message': {
            'ports': [chat_interface_el.ports.output['message_output']],
        },
        'schema': {
            'payload_type': SchemaPayload,
            'persist': True
        },
        'schema_template': {
            'role': 'system',
            'template': "The following is the schema you are required to comply with: \n {{ schema }}"
        }
    },
    trigger_map={
        'user_message': [
            'main_system_message_constant',
            '[history_system_message_constant]',
            '[history]',
            'user_query_system_message_constant',
            'user_message',
            'schema_template'
        ]
    }
)


initial_llm_chat_el = LLMChatElement(model_name='gpt-4o')
initial_context_builder_el.ports.messages_output > initial_llm_chat_el.ports.messages_emit_input
initial_llm_chat_el.ports.message_output > initial_llm_pipe_el.ports.pipe_input
initial_context_builder_el.ports.messages_output > initial_context_pipe_el.ports.pipe_input

structured_router_el = StructuredRouterTransformer(
    routing_map={
        'reply': {
            'schema': {'pydantic_model': str},
            'ports': [chat_interface_el.ports.message_input],
            'transform': lambda reply_content: MessagePayload(content=reply_content, role='assistant')
        },
        'tools': {
            'schema': {'payload_type': SchemaPayload},
            'payload_type': StructuredPayload
        }
    }
)

structured_router_el.ports.reply > reply_pipe_el.ports.pipe_input
structured_router_el.ports.tools > tools_pipe_el.ports.pipe_input

initial_llm_chat_el.ports.message_output > structured_router_el.ports.message_input

mcp_el = MCPElement(mcps={
    'test_mcp': {
        'type': 'script',
        'script': 'test_mcp_server.py',
    },
    'test_mcp2': {
        'type': 'script',
        'script': 'test_mcp_server2.py',
    }
})
mcp_el.ports.tools_schema_output > structured_router_el.ports.tools_schema_input
structured_router_el.ports.tools > mcp_el.ports.tool_request_structured_input
structured_router_el.ports.schema_output > initial_context_builder_el.ports.schema
mcp_el.ports.tool_response_output > chat_interface_el.ports.tools_response_input

#########
mcp_schema_pipe_el = PipeElement(receive_callback=lambda p: f"Schema from MCP received in pipe: {p.model.schema.model_json_schema()}")
mcp_el.ports.tools_schema_output > mcp_schema_pipe_el.ports.pipe_input
#########
schema_pipe_el = PipeElement(receive_callback=lambda p: f"Schema from StructuredRouterTransformer received in pipe: {p.model.schema.model_json_schema()}")
structured_router_el.ports.schema_output > schema_pipe_el.ports.pipe_input
#########

final_context_builder_el = ContextBuilderElement(
    input_map={
        'main_system_message_constant': {
            'role': 'system',
            'message': "Your objective is to respond to the user's query to your best ability"
                       "using the tool output you have received as well as the history of your previous"
                       "interactions with the user."
        },
        'history_system_message_constant': {
            'role': 'system',
            'message': "The following is a history of our previous interactions between us"
        },
        'history': {
            'payload_type': list[MessagePayload],
        },
        'tools': {
            'ports': [chat_interface_el.ports.tools_response_output]
        },
        'tools_template': { 
            'role': 'system',
            'template': "The following are the tool calls and their responses that you previously identified "
                        "as relevant to the user's query: \n {{ tools }}"
        },
        'query_system_message_constant': {
            'role': 'system',
            'message': "The following is the user's query to you."
        },
        'user_message': {
            'ports': [chat_interface_el.ports.message_output],
        }
    },
    trigger_map={
        'tools': [
            'main_system_message_constant',
            '[history_system_message_constant]',
            '[history]',
            'tools_template',
            'query_system_message_constant',
            'user_message'
        ]
    },
)

final_context_pipe_el = PipeElement(receive_callback=lambda ps: f"Final context pipe received: {ps}")
final_context_builder_el.ports.messages_output > final_context_pipe_el.ports.pipe_input


history_handler_el = HistoryHandlerElement()
history_handler_el.ports.message_history_output > initial_context_builder_el.ports.history
history_handler_el.ports.message_history_output > final_context_builder_el.ports.history
chat_interface_el.ports.output['message_output'] > history_handler_el.ports.messages_input
structured_router_el.ports.reply > history_handler_el.ports.messages_input


final_llm_chat_el = LLMChatElement(model_name='gpt-4o')
final_context_builder_el.ports.messages_output > final_llm_chat_el.ports.messages_emit_input
final_llm_chat_el.ports.message_output > history_handler_el.ports.message_emit_input
final_llm_chat_el.ports.message_output > chat_interface_el.ports.message_input

# from loguru import logger
# logger.debug(f"StructuredRouterTransformer: {structured_router_el.pydantic_model.model_json_schema()}")

@flow
def show_chat():
    # from pyllments.common.loop_registry import LoopRegistry
    return chat_interface_el.create_interface_view(height=800, width=600)

