from dataclasses import dataclass, field
import pathlib

from pyllments.elements import (
    ChatInterfaceElement,
    ContextBuilderElement,
    StructuredRouterTransformer,
    MCPElement,
    HistoryHandlerElement,
    LLMChatElement
)
from pyllments.payloads import MessagePayload, SchemaPayload, StructuredPayload
from pyllments import flow


@dataclass
class Config:
    height: int = field(
        default=850,
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
    custom_model: dict = field(
        default_factory=dict,
        metadata={
            "help": """
            Model name and base url for the model.
            '{"name": "ollama_chat/deepseek-r1:14b", "base_url": "http://172.17.0.3:11434"}'
            """
        }
    )
    model_name: str = field(
        default='gpt-4.1',
        metadata={
            "help": "The standard name of the model."
        }
    )
    mcp_dir: str = field(
        default='.',
        metadata={
            "help": "The directory containing the MCP server."
        }
    )

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
            'ports': [chat_interface_el.ports.user_message_output],
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

llm_chat_args = {
    'model_name': config.custom_model['name'],
    'base_url': config.custom_model['base_url']
} if config.custom_model else {'model_name': config.model_name}

initial_llm_chat_el = LLMChatElement(**llm_chat_args)

structured_router_el = StructuredRouterTransformer(
    routing_map={
        'reply': {
            'outputs': {
                'message': {
                    'schema': {'pydantic_model': str},
                    'ports': [chat_interface_el.ports.message_input],
                    'transform': lambda txt: MessagePayload(content=txt, role='assistant')
                }
            }
        },
        'tools': {
            'outputs': {
                'tools': {
                    'schema': {'payload_type': SchemaPayload},
                    'payload_type': StructuredPayload
                }
            }
        }
    }
)

# Connect initial context builder to initial LLM
initial_context_builder_el.ports.messages_output > initial_llm_chat_el.ports.messages_emit_input

# Connect initial LLM output to structured router
initial_llm_chat_el.ports.message_output > structured_router_el.ports.message_input

mcp_dir = pathlib.Path(config.mcp_dir)
mcp_files = list(mcp_dir.glob('*_mcp.py'))

mcp_args = {
    f.stem.replace('_mcp', ''): {
        'type': 'script',
        'script': str(f)
    }
    for f in mcp_files
}
mcp_el = MCPElement(mcps={**mcp_args})

# Connect MCP schema to structured router and structured router schema to initial context builder
mcp_el.ports.tools_schema_output > structured_router_el.ports.tools_tools_schema_input
structured_router_el.ports.tools_tools > mcp_el.ports.tool_request_structured_input
structured_router_el.ports.schema_output > initial_context_builder_el.ports.schema
mcp_el.ports.tools_response_output > chat_interface_el.ports.tools_response_emit_input

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
            'ports': [chat_interface_el.ports.user_message_output],
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

history_handler_el = HistoryHandlerElement()
history_handler_el.ports.message_history_output > initial_context_builder_el.ports.history
history_handler_el.ports.message_history_output > final_context_builder_el.ports.history
chat_interface_el.ports.user_message_output > history_handler_el.ports.messages_input
chat_interface_el.ports.tools_response_output > history_handler_el.ports.tools_responses_input
structured_router_el.ports.reply_message > history_handler_el.ports.message_emit_input

final_llm_chat_el = LLMChatElement(**llm_chat_args)
final_context_builder_el.ports.messages_output > final_llm_chat_el.ports.messages_emit_input
final_llm_chat_el.ports.message_output > history_handler_el.ports.message_emit_input
final_llm_chat_el.ports.message_output > chat_interface_el.ports.message_input

@flow
def show_chat():
    return chat_interface_el.create_interface_view(height=config.height, width=config.width)