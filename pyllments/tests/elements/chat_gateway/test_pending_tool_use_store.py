import tempfile
from pathlib import Path

import pytest

from pyllments.elements.chat_gateway import ChatGatewayElement, SQLitePendingToolUseStore
from pyllments.elements.history_handler.history_store import (
    _deserialize_tool_use,
    _serialize_tool_use,
)
from pyllments.elements import ToolUseElement
from pyllments.payloads import ToolUsePayload


@pytest.mark.asyncio
async def test_pending_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLitePendingToolUseStore(db_path=str(Path(tmp) / "pending.db"))
        payload = ToolUsePayload(executor_element_name="main_tools")
        payload.model.add_tool_call(
            adapter_name="functions",
            tool_name="secret",
            model_tool_name="functions_secret",
            permission_required=True,
        )
        from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseRecord

        record = PendingToolUseRecord(
            payload_data=_serialize_tool_use(payload),
            created_at=1.0,
            updated_at=1.0,
        )
        await store.upsert_record(record)
        assert record.rowid is not None
        loaded = await store.load_records()
        assert len(loaded) == 1
        restored = _deserialize_tool_use(loaded[0].payload_data)
        assert restored.model.executor_element_name == "main_tools"
        assert isinstance(restored.model.tool_calls, list)
        assert not restored.is_bound


@pytest.mark.asyncio
async def test_hydrate_pending_tool_uses_restores_permission_hook():
    def secret(value: str) -> str:
        return value

    with tempfile.TemporaryDirectory() as tmp:
        store = SQLitePendingToolUseStore(db_path=str(Path(tmp) / "pending.db"))
        tool_use_el = ToolUseElement(
            name="main_tools",
            functions=[secret],
            tools_requiring_permission=["secret"],
        )
        await tool_use_el.model.await_ready()

        payload = ToolUsePayload(executor_element_name="main_tools")
        index = payload.model.add_tool_call(
            adapter_name="functions",
            tool_name="secret",
            model_tool_name="functions_secret",
            parameters={"value": "x"},
            permission_required=True,
        )
        payload.model.apply_permission_request([index])

        from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseRecord

        await store.upsert_record(
            PendingToolUseRecord(
                payload_data=_serialize_tool_use(payload),
                created_at=1.0,
                updated_at=1.0,
            )
        )

        restored_requests = []
        gateway = ChatGatewayElement(
            pending_store=store,
            on_pending_permission_restored=lambda request: restored_requests.append(request),
        )
        restored = await gateway.hydrate_pending_tool_uses()

        assert len(restored) == 1
        assert len(restored_requests) == 1
        assert restored_requests[0].tools[0].name == "functions_secret"
        assert gateway.model.get_permission_request(restored_requests[0]) is not None


@pytest.mark.asyncio
async def test_hydrate_purges_when_executor_missing():
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLitePendingToolUseStore(db_path=str(Path(tmp) / "pending.db"))
        payload = ToolUsePayload(executor_element_name="missing_tools")
        payload.model.add_tool_call(
            adapter_name="functions",
            tool_name="secret",
            model_tool_name="functions_secret",
            permission_required=True,
        )
        index = payload.model.pending_permission_indices()[0]
        payload.model.apply_permission_request([index])

        from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseRecord

        await store.upsert_record(
            PendingToolUseRecord(
                payload_data=_serialize_tool_use(payload),
                created_at=1.0,
                updated_at=1.0,
            )
        )

        gateway = ChatGatewayElement(pending_store=store)
        restored = await gateway.hydrate_pending_tool_uses()

        assert restored == []
        assert await store.load_records() == []
