import pytest

from pydantic import RootModel, create_model

from pyllments.logging import setup_logging
from pyllments.elements import StructuredRouterTransformer, PipeElement, MCPElement
from pyllments.payloads import MessagePayload, StructuredPayload

from pathlib import Path

setup_logging()

SCRIPT_DIR = Path(__file__).parent.resolve()
PARENT_DIR = SCRIPT_DIR.parent
MCP_DIR = PARENT_DIR / 'mcp'

# @pytest.fixture
# def structured_router_transformer_pipe_el():
#     structured_router_transformer = StructuredRouterTransformer(
#         routing_map={
#             'reply': {
#                 'schema': {'pydantic_model': str},
#                 'payload_type': MessagePayload,
#             },
#             'other_reply': {
#                 'schema': {'pydantic_model': create_model('', wopwop=(str, ...), bop=(int, ...))},
#                 'payload_type': MessagePayload,
#             }
#         }
#     )
#     pipe_el = PipeElement(receive_callback=lambda x: x.model.schema.model_json_schema())
#     return structured_router_transformer, pipe_el

# def test_structured_router_transformer(structured_router_transformer_pipe_el):
#     structured_router_transformer, pipe_el = structured_router_transformer_pipe_el
#     structured_router_transformer.ports.schema_output > pipe_el.ports.pipe_input

# def test_structured_router_transformer_mcp_schema():
#     mcp_el = MCPElement(mcps={
#         'test_mcp': {
#             'type': 'script',
#             'script': str(MCP_DIR / 'test_mcp_server.py'),
#         },
#         'test_mcp2': {
#             'type': 'script',
#             'script': str(MCP_DIR / 'test_mcp_server2.py'),
#         }
#     })

#     structured_router_transformer = StructuredRouterTransformer(
#         routing_map={
#             'reply': {
#                 'schema': {'pydantic_model': str},
#                 'payload_type': MessagePayload
#             },
#             'tools': {
#                 'schema': {'ports': [mcp_el.ports.tool_list_schema_output]},
#                 'payload_type': MessagePayload
#             }
#         }
#     )

#     pipe_el = PipeElement(receive_callback=lambda x: x.model.schema.model_json_schema())
#     structured_router_transformer.ports.schema_output > pipe_el.ports.pipe_input

def test_structured_router_transformer_routes():
    mcp_el = MCPElement(mcps={
        'test_mcp': {
            'type': 'script',
            'script': str(MCP_DIR / 'test_mcp_server.py'),
        },
        'test_mcp2': {
            'type': 'script',
            'script': str(MCP_DIR / 'test_mcp_server2.py'),
        }
    })

    structured_router_transformer = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': StructuredPayload
            },
            'tools': {
                'schema': {'ports': [mcp_el.ports.tools_schema_output]},
                'payload_type': StructuredPayload
            }
        }
    )
    # Pipe element to receive the schema and pipe element to receive the tool list
    schema_receive_pipe_el = PipeElement(
        receive_callback=lambda x: x.model.schema.model_json_schema())
    route_receive_pipe_el = PipeElement(receive_callback=lambda x: x.model.data)
    route_send_pipe_el = PipeElement()

    route_send_pipe_el.ports.pipe_output > structured_router_transformer.ports.message_input
    structured_router_transformer.ports.schema_output > schema_receive_pipe_el.ports.pipe_input
    structured_router_transformer.ports.reply > route_receive_pipe_el.ports.pipe_input
    structured_router_transformer.ports.tools > route_receive_pipe_el.ports.pipe_input

    tools_js = '''
{
  "route": "tools",
  "tools": [
    {
      "name": "test_mcp_calculate",
      "parameters": {
        "operation": "multiply",
        "a": 6,
        "b": 7
      }
    },
    {
      "name": "test_mcp2_format_text",
      "parameters": {
        "text": "hello world",
        "format_type": "title"
      }
    },
    {
      "name": "test_mcp2_generate_password",
      "parameters": {
        "length": 8,
        "include_special": false
      }
    },
    {
      "name": "test_mcp_get_current_time"
    }
  ]
}
'''
    route_send_pipe_el.send_payload(MessagePayload(content=tools_js))
    
    reply_js = '''
{
  "route": "reply",
  "reply": "hello world"
}
'''
    route_send_pipe_el.send_payload(MessagePayload(content=reply_js))



