"""
Persistence for pending tool permission requests across application restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Protocol

from sqlite_utils import Database

from loguru import logger

logger = logger.bind(name=__name__)


@dataclass
class PendingToolUseRecord:
    """Serialized pending permission request for one ToolUsePayload."""

    payload_data: dict[str, Any]
    created_at: float
    updated_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    rowid: int | None = None


class PendingToolUseStore(Protocol):
    """Thin persistence contract for gateway pending tool permission state."""

    async def load_records(self) -> List[PendingToolUseRecord]: ...

    async def upsert_record(self, record: PendingToolUseRecord) -> None: ...

    async def delete_record(self, record: PendingToolUseRecord) -> None: ...


class SQLitePendingToolUseStore:
    """Local SQLite implementation of PendingToolUseStore."""

    TABLE_NAME = "pending_tool_use_records"

    def __init__(self, db_path: Optional[str] = None, name: str = "ChatGateway"):
        path = Path(db_path) if db_path else Path(f"{name}.db")
        if path.suffix != ".db":
            path = path / f"{name}_pending_tools.db"
        self.db_path = str(path)
        self.db = Database(self.db_path)
        self.table = self.db[self.TABLE_NAME]
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self.table.exists():
            return
        self.table.create(
            {
                "payload_data": str,
                "created_at": float,
                "updated_at": float,
                "metadata": str,
            },
        )

    async def load_records(self) -> List[PendingToolUseRecord]:
        rows = self.db.conn.execute(
            f"select rowid, payload_data, created_at, updated_at, metadata "
            f"from {self.TABLE_NAME} order by created_at"
        )
        records: List[PendingToolUseRecord] = []
        columns = [column[0] for column in rows.description]
        for row in rows:
            row = dict(zip(columns, row))
            try:
                records.append(
                    PendingToolUseRecord(
                        payload_data=json.loads(row["payload_data"]),
                        created_at=float(row["created_at"]),
                        updated_at=float(row["updated_at"]),
                        metadata=json.loads(row.get("metadata") or "{}"),
                        rowid=int(row["rowid"]),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to load pending tool record: %s",
                    exc,
                )
        return records

    async def upsert_record(self, record: PendingToolUseRecord) -> None:
        row = {
            "payload_data": json.dumps(record.payload_data),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": json.dumps(record.metadata),
        }
        with self.db.conn:
            if record.rowid is None:
                cursor = self.db.conn.execute(
                    f"insert into {self.TABLE_NAME} "
                    "(payload_data, created_at, updated_at, metadata) "
                    "values (?, ?, ?, ?)",
                    (
                        row["payload_data"],
                        row["created_at"],
                        row["updated_at"],
                        row["metadata"],
                    ),
                )
                record.rowid = cursor.lastrowid
                return
            self.db.conn.execute(
                f"update {self.TABLE_NAME} "
                "set payload_data = ?, created_at = ?, updated_at = ?, metadata = ? "
                "where rowid = ?",
                (
                    row["payload_data"],
                    row["created_at"],
                    row["updated_at"],
                    row["metadata"],
                    record.rowid,
                ),
            )

    async def delete_record(self, record: PendingToolUseRecord) -> None:
        if record.rowid is None:
            return
        with self.db.conn:
            self.db.conn.execute(
                f"delete from {self.TABLE_NAME} where rowid = ?",
                (record.rowid,),
            )
        record.rowid = None
