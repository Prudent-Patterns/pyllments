import tempfile
from pathlib import Path

import pytest

from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseSnapshot
from pyllments.elements.chat_gateway.sqlite_pending_tool_use_store import (
    SQLitePendingToolUseStore,
)
from pyllments.elements.history_handler.history_store import (
    _deserialize_tool_use,
    _serialize_tool_use,
)
from pyllments.payloads import ToolUsePayload


@pytest.mark.asyncio
async def test_sqlite_pending_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLitePendingToolUseStore(db_path=str(Path(tmp) / "pending.db"))
        payload = ToolUsePayload(executor_element_name="main_tools")
        payload.model.add_tool_call(
            adapter_name="functions",
            tool_name="secret",
            model_tool_name="functions_secret",
            permission_required=True,
        )

        snapshot = PendingToolUseSnapshot(
            payload_data=_serialize_tool_use(payload),
            created_at=1.0,
            updated_at=1.0,
        )
        saved = await store.save_pending_tool_use(snapshot)
        assert saved.id is not None

        loaded = await store.load_pending_tool_uses()
        assert len(loaded) == 1
        restored = _deserialize_tool_use(loaded[0].payload_data)
        assert restored.model.executor_element_name == "main_tools"
        assert isinstance(restored.model.tool_calls, list)
        assert not restored.is_bound

        await store.clear_pending_tool_use(loaded[0])
        assert await store.load_pending_tool_uses() == []
