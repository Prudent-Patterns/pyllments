"""ContextBuilder converts mixed payload lists from HistoryHandler context_output."""

from pyllments.elements.context_builder.context_builder_element import ContextBuilderElement
from pyllments.payloads import MessagePayload, ToolUsePayload


def test_mixed_payload_list_converts_per_item():
    cb = ContextBuilderElement(input_map={}, emit_order=[])
    msg = MessagePayload(role="user", content="hello")
    tool = ToolUsePayload(executor_element_name="main_tools")
    tool.model.add_tool_use(
        adapter_name="mcp",
        provider_name="m",
        tool_name="fn",
        model_tool_name="m_fn",
    )
    tool_use_id = next(iter(tool.model.tool_uses))
    tool.model.attach_result(
        tool_use_id,
        {"content": [{"type": "text", "text": "ok"}], "raw": None, "metadata": {}},
    )
    result = cb._convert_payload_to_message("history", [msg, tool])
    assert len(result) == 2
    assert result[0].model.role == "user"
    assert result[1].model.role == "system"
