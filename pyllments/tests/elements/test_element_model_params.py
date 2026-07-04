"""Constructor forwarding from elements to models."""

from pydantic import create_model

from pyllments.elements.chat_gateway import ChatGatewayElement
from pyllments.elements.file_loader import FileLoaderElement
from pyllments.elements.structured_output import StructuredOutputElement
from pyllments.elements.tool_use import ToolUseElement


def add(a: int, b: int) -> int:
    return a + b


def test_file_loader_forwards_model_params():
    element = FileLoaderElement(file_dir="/tmp/files", save_to_disk=True)
    assert element.model.file_dir == "/tmp/files"
    assert element.model.save_to_disk is True


def test_structured_output_forwards_model_params():
    schema = create_model("Reply", text=(str, ...))
    element = StructuredOutputElement(schema=schema, auto_emit_schema=False)
    assert element.model.schema is schema


def test_tool_use_forwards_model_params():
    element = ToolUseElement(name="main_tools", functions=[add])
    assert element.name == "main_tools"
    assert element.model.adapters


def test_gateway_forwards_hook_params_to_model():
    def on_tool_use(review):
        return None

    gateway = ChatGatewayElement(on_tool_use=on_tool_use)
    assert gateway.model.on_tool_use is on_tool_use


def test_gateway_pending_store_is_element_param_not_model_state():
    sentinel = object()
    gateway = ChatGatewayElement(pending_store=sentinel)
    assert "pending_store" in gateway.param
    assert gateway.pending_store is sentinel
    assert not hasattr(gateway.model, "pending_store")
