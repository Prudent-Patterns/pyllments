import pytest

from pyllments.elements import ChatGatewayElement, PipeElement, ToolUseElement
from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseSnapshot
from pyllments.elements.history_handler.history_store import (
    _deserialize_tool_use,
    _serialize_tool_use,
)
from pyllments.payloads import StructuredPayload, ToolUsePayload


class InMemoryPendingToolUseStore:
    """Test double for app-owned pending tool persistence."""

    def __init__(self):
        self._snapshots: dict[str, PendingToolUseSnapshot] = {}
        self._counter = 0

    async def load_pending_tool_uses(self) -> list[PendingToolUseSnapshot]:
        return list(self._snapshots.values())

    async def save_pending_tool_use(
        self, snapshot: PendingToolUseSnapshot
    ) -> PendingToolUseSnapshot:
        if snapshot.id is None:
            self._counter += 1
            snapshot.id = f"mem-{self._counter}"
        self._snapshots[snapshot.id] = snapshot
        return snapshot

    async def clear_pending_tool_use(self, snapshot: PendingToolUseSnapshot) -> None:
        if snapshot.id is not None:
            self._snapshots.pop(snapshot.id, None)
        snapshot.id = None


@pytest.mark.asyncio
async def test_pending_store_roundtrip():
    store = InMemoryPendingToolUseStore()
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


@pytest.mark.asyncio
async def test_hydrate_pending_tool_uses_restores_permission_hook():
    def secret(value: str) -> str:
        return value

    store = InMemoryPendingToolUseStore()
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

    await store.save_pending_tool_use(
        PendingToolUseSnapshot(
            payload_data=_serialize_tool_use(payload),
            created_at=1.0,
            updated_at=1.0,
        )
    )

    restored_reviews = []
    gateway = ChatGatewayElement(
        pending_store=store,
        on_pending_tool_use_restored=lambda review: restored_reviews.append(review),
    )
    restored = await gateway.hydrate_pending_tool_uses()

    assert len(restored) == 1
    assert len(restored_reviews) == 1
    assert restored_reviews[0]["tools"][0]["name"] == "functions_secret"
    assert gateway.model.get_pending_tool_use(restored_reviews[0]) is not None


@pytest.mark.asyncio
async def test_hydrate_purges_when_executor_missing():
    store = InMemoryPendingToolUseStore()
    payload = ToolUsePayload(executor_element_name="missing_tools")
    payload.model.add_tool_call(
        adapter_name="functions",
        tool_name="secret",
        model_tool_name="functions_secret",
        permission_required=True,
    )
    index = payload.model.pending_permission_indices()[0]
    payload.model.apply_permission_request([index])

    await store.save_pending_tool_use(
        PendingToolUseSnapshot(
            payload_data=_serialize_tool_use(payload),
            created_at=1.0,
            updated_at=1.0,
        )
    )

    gateway = ChatGatewayElement(pending_store=store)
    restored = await gateway.hydrate_pending_tool_uses()

    assert restored == []
    assert await store.load_pending_tool_uses() == []


@pytest.mark.asyncio
async def test_resolve_clears_pending_snapshot():
    def secret(value: str) -> str:
        return value

    store = InMemoryPendingToolUseStore()
    tool_use_el = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    await tool_use_el.model.await_ready()

    reviews: list[dict] = []
    gateway = ChatGatewayElement(
        pending_store=store,
        on_tool_use=lambda review: reviews.append(review) or None,
    )
    tools_pipe = PipeElement(name="tools_pipe")
    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    tools_pipe.ports.output["pipe_output"] > tool_use_el.ports.tool_request_structured_input

    await gateway.submit_message_async("Delete this")
    await gateway.ports.output["message_output"].drain()

    await tools_pipe.async_send_payload(
        StructuredPayload(
            data=[{"name": "functions_secret", "parameters": {"value": "x"}}]
        )
    )
    await tool_use_el.ports.output["tool_use_output"].drain()
    assert len(await store.load_pending_tool_uses()) == 1

    review = reviews[0]
    await gateway.resolve_tool_use(
        review,
        {"decisions": [{"decision": "approved"}]},
    )
    await gateway.ports.output["tool_result_output"].drain()

    assert await store.load_pending_tool_uses() == []
    assert gateway.model._pending_tool_uses == []


@pytest.mark.asyncio
async def test_supersede_clears_pending_snapshot():
    def secret(value: str) -> str:
        return value

    store = InMemoryPendingToolUseStore()
    tool_use_el = ToolUseElement(
        name="main_tools",
        functions=[secret],
        tools_requiring_permission=["secret"],
    )
    await tool_use_el.model.await_ready()

    reviews: list[dict] = []
    gateway = ChatGatewayElement(
        pending_store=store,
        on_tool_use=lambda review: reviews.append(review) or None,
    )
    tools_pipe = PipeElement(name="tools_pipe")
    tool_use_el.ports.tool_use_output > gateway.ports.input["tool_use_input"]
    tools_pipe.ports.output["pipe_output"] > tool_use_el.ports.tool_request_structured_input

    await gateway.submit_message_async("first")
    await gateway.ports.output["message_output"].drain()

    await tools_pipe.async_send_payload(
        StructuredPayload(
            data=[{"name": "functions_secret", "parameters": {"value": "x"}}]
        )
    )
    await tool_use_el.ports.output["tool_use_output"].drain()
    assert len(await store.load_pending_tool_uses()) == 1

    await gateway.submit_message_async("replacement")
    await gateway.ports.output["message_output"].drain()

    assert await store.load_pending_tool_uses() == []
    assert gateway.model._pending_tool_uses == []
