import asyncio

from pyllments.elements import PipeElement, ToolUseElement
from pyllments.payloads import StructuredPayload
from pyllments.runtime.loop_registry import LoopRegistry


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


async def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


def secret(value: str) -> str:
    """Access secret data."""
    return value


def run_loop_briefly(duration=0.2):
    loop = LoopRegistry.get_loop()
    stop_time = loop.time() + duration
    while loop.time() < stop_time:
        loop.run_until_complete(asyncio.sleep(0.01))


def test_function_tools_schema():
    element = ToolUseElement(functions=[add])
    pipe = PipeElement(name="schema_pipe")
    loop = LoopRegistry.get_loop()

    element.ports.tools_schema_output > pipe.ports.pipe_input
    loop.run_until_complete(element.model.await_ready())
    run_loop_briefly()

    assert "functions_add" in element.model.tool_specs
    assert len(pipe.received_payloads) > 0
    assert pipe.received_payloads[0].model.schema is not None


def test_function_tool_execution():
    element = ToolUseElement(functions=[add])
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")
    loop = LoopRegistry.get_loop()

    element.ports.tool_result_output > result_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    loop.run_until_complete(element.model.await_ready())

    request_pipe.send_payload(
        StructuredPayload(data=[{"name": "functions_add", "parameters": {"a": 1, "b": 2}}])
    )
    run_loop_briefly(duration=0.5)

    assert len(result_pipe.received_payloads) > 0
    payload = result_pipe.received_payloads[0]
    tool_uses = payload.model.tool_uses
    assert any(record.get("status") == "succeeded" for record in tool_uses.values())
    assert "3" in payload.model.content


def test_async_function_tool():
    element = ToolUseElement(functions=[multiply])
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")
    loop = LoopRegistry.get_loop()

    element.ports.tool_result_output > result_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    loop.run_until_complete(element.model.await_ready())

    request_pipe.send_payload(
        StructuredPayload(data=[{"name": "functions_multiply", "parameters": {"a": 3, "b": 4}}])
    )
    run_loop_briefly(duration=0.5)

    assert len(result_pipe.received_payloads) > 0
    payload = result_pipe.received_payloads[0]
    assert any(record.get("status") == "succeeded" for record in payload.model.tool_uses.values())
    assert "12" in payload.model.content


def test_permission_gating():
    element = ToolUseElement(
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    tool_use_pipe = PipeElement(name="tool_use_pipe")
    result_pipe = PipeElement(name="result_pipe")
    request_pipe = PipeElement(name="request_pipe")
    loop = LoopRegistry.get_loop()

    element.ports.tool_use_output > tool_use_pipe.ports.pipe_input
    element.ports.tool_result_output > result_pipe.ports.pipe_input
    request_pipe.ports.pipe_output > element.ports.tool_request_structured_input

    loop.run_until_complete(element.model.await_ready())

    request_pipe.send_payload(
        StructuredPayload(data=[{"name": "functions_secret", "parameters": {"value": "hidden"}}])
    )
    run_loop_briefly(duration=0.5)

    assert len(tool_use_pipe.received_payloads) == 1
    payload = tool_use_pipe.received_payloads[0]
    assert payload.model.needs_permission()
    assert payload.model.status == "awaiting_permission"
    assert len(result_pipe.received_payloads) == 0
