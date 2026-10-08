"""The function adapter: schema from signatures, plain names, JSON results."""

import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

import pytest

from pyllments.elements.tool_use.function_tool_adapter import FunctionToolAdapter, result_text
from pyllments.elements.tool_use.signature_schema import parameters_schema, validate_arguments

_REPO_ROOT = str(Path(__file__).resolve().parents[4])


def search(query: str, types: list[str] = (), limit: int = 10, kind: Literal["plan", "note"] = "plan",
           cursor: Optional[str] = None) -> dict:
    """Find this person's records."""
    return {"query": query, "limit": limit}


def test_schema_reads_the_signature():
    schema, accepts_context = parameters_schema(search)
    assert not accepts_context
    assert schema["required"] == ["query"]
    assert schema["properties"]["query"] == {"type": "string"}
    # A tuple default is written as a list: the schema must survive JSON and an RPC boundary.
    assert schema["properties"]["types"] == {"type": "array", "items": {"type": "string"}, "default": []}
    assert schema["properties"]["limit"] == {"type": "integer", "default": 10}
    assert schema["properties"]["kind"] == {"enum": ["plan", "note"], "default": "plan"}
    assert schema["properties"]["cursor"]["anyOf"] == [{"type": "string"}, {"type": "null"}]


def test_validation_names_every_problem():
    schema, _ = parameters_schema(search)
    with pytest.raises(ValueError) as excinfo:
        validate_arguments(schema, {"limit": "ten", "extra": 1})
    message = str(excinfo.value)
    assert "missing required argument(s): query" in message
    assert "unknown argument(s): extra" in message
    assert "wrong type for: limit (expected integer)" in message
    assert validate_arguments(schema, {"query": "x", "cursor": None}) == {"query": "x", "cursor": None}


@pytest.mark.asyncio
async def test_plain_names_and_json_results():
    adapter = FunctionToolAdapter(functions=[search], prefix_names=False)
    tools = await adapter.list_tools()
    assert list(tools) == ["search"]
    assert tools["search"].description == "Find this person's records."
    result = await adapter.call_tool(provider_name=None, tool_name="search", parameters={"query": "a"})
    assert result.content[0]["text"] == '{"query": "a", "limit": 10}'
    assert result.raw == {"value": {"query": "a", "limit": 10}}


def test_prefixed_names_stay_the_default():
    assert FunctionToolAdapter(functions=[search]).model_tool_name("search") == "functions_search"


def test_result_text_forms():
    assert result_text("plain") == "plain"
    assert result_text(None) == ""
    assert result_text([1, 2]) == "[1, 2]"
    assert result_text(3.5) == "3.5"


def test_function_tools_run_without_pydantic():
    script = """
import asyncio, sys
from pyllments.elements.tool_use import ToolUseElement
from pyllments.payloads import ToolUsePayload

def add(a: int, b: int) -> int:
    return a + b

async def main():
    element = ToolUseElement(name="t", functions=[add], prefix_names=False)
    await element.model.await_ready()
    payload = ToolUsePayload(executor_element_name="t")
    i = payload.model.add_tool_call(adapter_name="functions", tool_name="add", model_tool_name="add", parameters={"a": 2, "b": 3})
    payload.bind_executor(element)
    await element.execute_tool_use_payload(payload, tool_call_indices=[i])
    assert payload.model.tool_calls[i]["result"]["content"][0]["text"] == "5"
    assert "pydantic" not in sys.modules, "pydantic loaded on the tool path"
    assert "mcp" not in sys.modules

asyncio.run(main())
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=_REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_json_text_arguments_are_read_as_the_values_they_spell():
    # Llama-class models send `types` as the JSON text of a list; the call must still run.
    schema, _ = parameters_schema(search)
    out = validate_arguments(schema, {"query": "prednisone", "types": '["medication"]', "limit": "5"})
    assert out["types"] == ["medication"] and out["limit"] == 5
    with pytest.raises(ValueError, match="wrong type for: types"):
        validate_arguments(schema, {"query": "x", "types": "medication"})


def test_empty_and_null_strings_mean_not_given_for_optional_parameters():
    schema, _ = parameters_schema(search)
    out = validate_arguments(schema, {"query": "walking", "kind": "", "cursor": "null", "limit": "10"})
    assert out == {"query": "walking", "limit": 10}
    with pytest.raises(ValueError, match="missing required argument"):
        validate_arguments(schema, {"query": ""} if False else {"kind": "goal"})

