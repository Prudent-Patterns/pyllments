"""
Backend-neutral persistence contract for HistoryHandler raw ledger records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Type
from uuid import uuid4

from sqlite_utils import Database

from pyllments.payloads import MessagePayload, StructuredPayload, ToolUsePayload
from loguru import logger

logger = logger.bind(name=__name__)

PayloadSerializer = Callable[[Any], dict]
PayloadDeserializer = Callable[[dict], Any]

_SERIALIZERS: Dict[str, PayloadSerializer] = {}
_DESERIALIZERS: Dict[str, PayloadDeserializer] = {}


def _payload_timestamp(payload: Any) -> float:
    data = getattr(getattr(payload, "model", None), "data", None)
    if isinstance(data, dict) and data.get("timestamp") is not None:
        return float(data["timestamp"])
    return float(getattr(payload.model, "timestamp", 0) or 0)


def register_payload_serializer(
    payload_type: Type,
    serializer: PayloadSerializer,
    deserializer: PayloadDeserializer,
) -> None:
    """Register serialize/deserialize helpers for a payload class name."""
    key = payload_type.__name__
    _SERIALIZERS[key] = serializer
    _DESERIALIZERS[key] = deserializer


def _serialize_message(payload: MessagePayload) -> dict:
    return {
        "role": payload.model.role,
        "content": payload.model.content,
        "mode": payload.model.mode,
        "timestamp": payload.model.timestamp,
    }


def _deserialize_message(data: dict) -> MessagePayload:
    return MessagePayload(
        role=data["role"],
        content=data["content"],
        mode=data.get("mode", "atomic"),
        timestamp=data["timestamp"],
    )


def _serialize_tool_use(payload: ToolUsePayload) -> dict:
    return {
        "flow_id": payload.model.flow_id,
        "flow_version": payload.model.flow_version,
        "executor_element_name": payload.model.executor_element_name,
        "status": payload.model.status,
        "tool_calls": payload.model.tool_calls,
        "metadata": payload.model.metadata,
        "timestamp": payload.model.timestamp,
        "updated_at": payload.model.updated_at,
    }


def _deserialize_tool_use(data: dict) -> ToolUsePayload:
    return ToolUsePayload(
        flow_id=data.get("flow_id"),
        flow_version=data.get("flow_version"),
        executor_element_name=data.get("executor_element_name"),
        status=data.get("status", "pending"),
        tool_calls=data.get("tool_calls", []),
        metadata=data.get("metadata", {}),
        timestamp=data.get("timestamp"),
        updated_at=data.get("updated_at"),
    )


register_payload_serializer(MessagePayload, _serialize_message, _deserialize_message)
register_payload_serializer(
    ToolUsePayload,
    _serialize_tool_use,
    _deserialize_tool_use,
)


def _serialize_structured(payload: StructuredPayload) -> dict:
    return {"data": payload.model.data}


def _deserialize_structured(data: dict) -> StructuredPayload:
    return StructuredPayload(data=data.get("data", data))


register_payload_serializer(
    StructuredPayload,
    _serialize_structured,
    _deserialize_structured,
)


def payload_to_record(entry_id: str, payload: Any, raw_token_count: int, summarized: bool = False) -> Optional["HistoryRecord"]:
    """Build a HistoryRecord from a payload, or None if unsupported."""
    payload_type = type(payload).__name__
    serializer = _SERIALIZERS.get(payload_type)
    if serializer is None:
        logger.warning("No serializer for payload type %s; skipping persistence.", payload_type)
        return None
    ts = _payload_timestamp(payload)
    return HistoryRecord(
        entry_id=entry_id,
        timestamp=ts,
        payload_type=payload_type,
        payload_data=serializer(payload),
        raw_token_count=raw_token_count,
        summarized=summarized,
    )


def record_to_payload(record: HistoryRecord) -> Optional[Any]:
    """Reconstruct a payload from a HistoryRecord."""
    deserializer = _DESERIALIZERS.get(record.payload_type)
    if deserializer is None:
        logger.warning("No deserializer for payload type %s", record.payload_type)
        return None
    return deserializer(record.payload_data)


def new_entry_id() -> str:
    return str(uuid4())


@dataclass
class HistoryRecord:
    """Serialized raw ledger row; projection is never stored."""

    entry_id: str
    timestamp: float
    payload_type: str
    payload_data: dict
    raw_token_count: int
    summarized: bool = False
    metadata: dict = field(default_factory=dict)


class HistoryStore(Protocol):
    """Thin persistence contract for raw history records."""

    async def load_records(self) -> List[HistoryRecord]: ...

    async def append_records(self, records: List[HistoryRecord]) -> None: ...

    async def delete_records(self, entry_ids: List[str]) -> None: ...

    async def mark_summarized(self, entry_ids: List[str]) -> None: ...


class SQLiteHistoryStore:
    """Local SQLite implementation of HistoryStore."""

    TABLE_NAME = "history_records"

    def __init__(self, db_path: Optional[str] = None, name: str = "HistoryHandlerModel"):
        path = Path(db_path) if db_path else Path(f"{name}.db")
        if path.suffix != ".db":
            path = path / f"{name}.db"
        self.db_path = str(path)
        self.db = Database(self.db_path)
        self.table = self.db[self.TABLE_NAME]
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self.table.exists():
            return
        self.table.create(
            {
                "entry_id": str,
                "timestamp": float,
                "payload_type": str,
                "payload_data": str,
                "raw_token_count": int,
                "summarized": int,
                "metadata": str,
            },
            pk="entry_id",
        )

    async def load_records(self) -> List[HistoryRecord]:
        rows = self.table.rows_where(order_by="timestamp")
        records: List[HistoryRecord] = []
        for row in rows:
            try:
                records.append(
                    HistoryRecord(
                        entry_id=row["entry_id"],
                        timestamp=float(row["timestamp"]),
                        payload_type=row["payload_type"],
                        payload_data=json.loads(row["payload_data"]),
                        raw_token_count=int(row["raw_token_count"]),
                        summarized=bool(row["summarized"]),
                        metadata=json.loads(row.get("metadata") or "{}"),
                    )
                )
            except Exception as exc:
                logger.warning("Failed to load history record %s: %s", row.get("entry_id"), exc)
        return records

    async def append_records(self, records: List[HistoryRecord]) -> None:
        if not records:
            return
        rows = [
            {
                "entry_id": r.entry_id,
                "timestamp": r.timestamp,
                "payload_type": r.payload_type,
                "payload_data": json.dumps(r.payload_data),
                "raw_token_count": r.raw_token_count,
                "summarized": int(r.summarized),
                "metadata": json.dumps(r.metadata),
            }
            for r in records
        ]
        with self.db.conn:
            self.table.insert_all(rows)

    async def delete_records(self, entry_ids: List[str]) -> None:
        if not entry_ids:
            return
        with self.db.conn:
            self.table.delete_where(
                "entry_id IN (" + ",".join("?" * len(entry_ids)) + ")",
                entry_ids,
            )

    async def mark_summarized(self, entry_ids: List[str]) -> None:
        if not entry_ids:
            return
        with self.db.conn:
            for entry_id in entry_ids:
                self.table.update(entry_id, {"summarized": 1})
