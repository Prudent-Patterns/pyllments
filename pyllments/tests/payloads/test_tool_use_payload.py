import pytest

from pyllments.payloads import ToolUsePayload


def test_tool_use_payload_lifecycle():
    payload = ToolUsePayload(
        executor_element_name="main_tools",
        turn_id="turn-1",
    )
    tool_use_id = payload.model.add_tool_use(
        adapter_name="functions",
        tool_name="ping",
        model_tool_name="functions_ping",
        parameters={"x": 1},
        permission_required=True,
    )
    assert payload.model.needs_permission()
    payload.model.apply_permission_request("perm-1")
    assert payload.model.tool_uses[tool_use_id]["status"] == "awaiting_permission"

    payload.model.approve()
    assert payload.model.can_execute(tool_use_id)
    payload.model.attach_result(
        tool_use_id,
        {"content": [{"type": "text", "text": "pong"}], "raw": None, "metadata": {}},
    )
    assert payload.model.completed
    assert "pong" in payload.model.content


def test_tool_use_payload_denial():
    payload = ToolUsePayload(executor_element_name="main_tools")
    payload.model.add_tool_use(
        adapter_name="mcp",
        provider_name="fs",
        tool_name="delete",
        model_tool_name="fs_delete",
        permission_required=True,
    )
    payload.model.deny(reason="nope")
    assert payload.model.completed
    assert "denied" in payload.model.content.lower() or payload.model.status == "completed"
