"""ContextBuilder converts mixed payload lists from HistoryHandler context_output."""

from pyllments.elements.context_builder.context_builder_element import ContextBuilderElement
from pyllments.payloads import MessagePayload, ToolsResponsePayload


def test_mixed_payload_list_converts_per_item():
    cb = ContextBuilderElement(input_map={}, emit_order=[])
    msg = MessagePayload(role="user", content="hello")
    tool = ToolsResponsePayload(
        tool_responses={
            "t": {
                "mcp_name": "m",
                "tool_name": "fn",
                "response": {"content": [{"type": "text", "text": "ok"}]},
            }
        },
    )
    result = cb._convert_payload_to_message("history", [msg, tool])
    assert len(result) == 2
    assert result[0].model.role == "user"
    assert result[1].model.role == "system"
