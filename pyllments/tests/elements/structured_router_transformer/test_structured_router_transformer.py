import pytest

from pydantic import RootModel, create_model

from pyllments.logging import setup_logging
from pyllments.elements import StructuredRouterTransformer, PipeElement, MCPElement
from pyllments.payloads import MessagePayload, StructuredPayload
from pyllments.common.loop_registry import LoopRegistry

from pathlib import Path
import asyncio

setup_logging()

SCRIPT_DIR = Path(__file__).parent.resolve()
PARENT_DIR = SCRIPT_DIR.parent
MCP_DIR = PARENT_DIR / 'mcp'

@pytest.fixture
def structured_router_transformer_pipe_el():
    structured_router_transformer = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': MessagePayload,
            },
            'other_reply': {
                'schema': {'pydantic_model': create_model('', wopwop=(str, ...), bop=(int, ...))},
                'payload_type': MessagePayload,
            }
        }
    )
    pipe_el = PipeElement(receive_callback=lambda x: x.model.schema.model_json_schema())
    return structured_router_transformer, pipe_el

def test_structured_router_transformer(structured_router_transformer_pipe_el):
    structured_router_transformer, pipe_el = structured_router_transformer_pipe_el
    structured_router_transformer.ports.schema_output > pipe_el.ports.pipe_input

def test_structured_router_transformer_mcp_schema():
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
                'payload_type': MessagePayload
            },
            'tools': {
                'schema': {'ports': [mcp_el.ports.tools_schema_output]},
                'payload_type': MessagePayload
            }
        }
    )

    pipe_el = PipeElement(receive_callback=lambda x: x.model.schema.model_json_schema())
    structured_router_transformer.ports.schema_output > pipe_el.ports.pipe_input

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

def test_simple_structured_router_flow():
    """
    Simple test to verify the flow function in StructuredRouterTransformer gets called.
    Uses existing logging to debug the issue.
    """
    # Create a simple router
    structured_router = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': StructuredPayload
            }
        }
    )
    
    # Simple pipe to send input
    send_pipe = PipeElement()
    send_pipe.ports.pipe_output > structured_router.ports.message_input
    
    # Send a valid payload to trigger the flow function
    reply_json = '{"route": "reply", "reply": "test message"}'
    send_pipe.send_payload(MessagePayload(content=reply_json))
    
    # The logging in the flow function should show if it gets called

def test_debug_flow_fn_execution():
    """
    Test specifically focused on whether the flow function is being called,
    with explicit logging added to debug the issue.
    """
    from loguru import logger
    import inspect
    
    # Create a simple router with minimal configuration
    structured_router = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': StructuredPayload
            }
        }
    )
    
    # Add debug logging to verify function signatures and execution
    original_flow_fn = structured_router.flow_controller.flow_fn
    flow_fn_source = inspect.getsource(original_flow_fn)
    logger.debug(f"Flow function source:\n{flow_fn_source}")
    
    # Override the flow function to add explicit logging
    old_flow_fn = structured_router.flow_controller.flow_fn
    
    def debug_flow_fn(**kwargs):
        logger.debug(f"DEBUG: Flow function called with kwargs: {list(kwargs.keys())}")
        try:
            result = old_flow_fn(**kwargs)
            logger.debug("DEBUG: Flow function completed successfully")
            return result
        except Exception as e:
            logger.error(f"DEBUG: Flow function failed with error: {type(e).__name__}: {e}")
            raise
    
    structured_router.flow_controller.flow_fn = debug_flow_fn
    
    # Debug the _invoke_flow method directly
    old_invoke_flow = structured_router.flow_controller._invoke_flow
    
    def debug_invoke_flow(input_port_name, payload):
        logger.debug(f"DEBUG: _invoke_flow called for port {input_port_name}")
        return old_invoke_flow(input_port_name, payload)
    
    structured_router.flow_controller._invoke_flow = debug_invoke_flow
    
    # Add debug to the unpack_payload_callback
    for port_name, port in structured_router.ports.input.items():
        old_callback = port.unpack_payload_callback
        def debug_unpack(payload, old_cb=old_callback):
            logger.debug(f"DEBUG: unpack_payload_callback for port {port_name}")
            return old_cb(payload)
        port.unpack_payload_callback = debug_unpack
    
    # Set up pipe element to send input
    send_pipe = PipeElement()
    send_pipe.ports.pipe_output > structured_router.ports.message_input
    
    # Send a valid payload to trigger the flow function
    reply_json = '{"route": "reply", "reply": "test message"}'
    logger.debug(f"DEBUG: Sending payload: {reply_json}")
    send_pipe.send_payload(MessagePayload(content=reply_json))
    
    # Add some delay to allow async operations to complete
    import time
    time.sleep(0.1)
    
    logger.debug("DEBUG: Test complete")

def test_manually_await_flow_fn():
    """
    Test that manually awaits the flow function to see if the issue is that
    the async flow function is not being properly awaited.
    """
    from loguru import logger
    import asyncio
    
    # Create a simple router with minimal configuration
    structured_router = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': StructuredPayload
            }
        }
    )
    
    # Create a MessagePayload with the test JSON
    reply_json = '{"route": "reply", "reply": "test message"}'
    message_payload = MessagePayload(content=reply_json)
    
    # Get the message input port's flow port
    message_input_port = structured_router.flow_controller.flow_port_map['message_input']
    message_input_port.payload = message_payload
    
    # Create mock kwargs similar to what _invoke_flow would create
    reply_port = structured_router.flow_controller.flow_port_map['reply']
    kwargs = {
        'active_input_port': message_input_port,
        'c': structured_router.flow_controller.context,
        'message_input': message_input_port,
        'reply': reply_port
    }
    
    # Call the flow function directly and get the coroutine
    flow_coro = structured_router.flow_controller.flow_fn(**kwargs)
    
    # Check if it's actually a coroutine
    logger.debug(f"Is flow result a coroutine? {asyncio.iscoroutine(flow_coro)}")
    
    if asyncio.iscoroutine(flow_coro):
        # Manually run the coroutine in a new event loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            logger.debug("Manually awaiting flow function coroutine")
            loop.run_until_complete(flow_coro)
            logger.debug("Coroutine completed")
        finally:
            loop.close()
            asyncio.set_event_loop(None)

def test_loop_execution():
    """
    Test that runs the event loop briefly after sending a payload to check
    if loop execution is the issue.
    """
    from loguru import logger
    
    # Create a simple router with persist=True to avoid payload clearing
    structured_router = StructuredRouterTransformer(
        routing_map={
            'reply': {
                'schema': {'pydantic_model': str},
                'payload_type': StructuredPayload
            }
        }
    )
    
    # Manually modify the flow_map to set persist=True
    structured_router.flow_controller.flow_map['input']['message_input']['persist'] = True
    
    # Add a receiver to verify output
    output_received = False
    
    def capture_output(payload):
        nonlocal output_received
        output_received = True
        logger.debug(f"Output received: {payload.model.data}")
        return payload
    
    receiver_pipe = PipeElement(receive_callback=capture_output)
    
    # Set up pipes
    send_pipe = PipeElement()
    send_pipe.ports.pipe_output > structured_router.ports.message_input
    structured_router.ports.reply > receiver_pipe.ports.pipe_input
    
    # Helper function to run the loop briefly
    def run_loop_briefly():
        loop = LoopRegistry.get_loop()
        logger.debug("Running event loop until it's empty")
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending))
        logger.debug("Event loop run completed")
    
    # Send a valid payload
    reply_json = '{"route": "reply", "reply": "test message"}'
    logger.debug(f"Sending payload: {reply_json}")
    send_pipe.send_payload(MessagePayload(content=reply_json))
    
    # Run the loop briefly to process any pending tasks
    run_loop_briefly()
    
    # Check if we received output
    assert output_received, "Output was not received - the flow function's async tasks didn't complete"



