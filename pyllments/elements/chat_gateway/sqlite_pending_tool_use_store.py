"""
Optional SQLite adapter for :class:`~pyllments.elements.chat_gateway.pending_tool_use_store.PendingToolUseStore`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sqlite_utils import Database

from loguru import logger

from pyllments.elements.chat_gateway.pending_tool_use_store import PendingToolUseSnapshot

logger = logger.bind(name=__name__)


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

    async def load_pending_tool_uses(self) -> list[PendingToolUseSnapshot]:
        rows = self.db.conn.execute(
            f"select rowid, payload_data, created_at, updated_at, metadata "
            f"from {self.TABLE_NAME} order by created_at"
        )
        snapshots: list[PendingToolUseSnapshot] = []
        columns = [column[0] for column in rows.description]
        for row in rows:
            row = dict(zip(columns, row))
            try:
                snapshots.append(
                    PendingToolUseSnapshot(
                        id=str(row["rowid"]),
                        payload_data=json.loads(row["payload_data"]),
                        created_at=float(row["created_at"]),
                        updated_at=float(row["updated_at"]),
                        metadata=json.loads(row.get("metadata") or "{}"),
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Failed to load pending tool snapshot: %s",
                    exc,
                )
        return snapshots

    async def save_pending_tool_use(
        self, snapshot: PendingToolUseSnapshot
    ) -> PendingToolUseSnapshot:
        row = {
            "payload_data": json.dumps(snapshot.payload_data),
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
            "metadata": json.dumps(snapshot.metadata),
        }
        with self.db.conn:
            if snapshot.id is None:
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
                snapshot.id = str(cursor.lastrowid)
                return snapshot
            self.db.conn.execute(
                f"update {self.TABLE_NAME} "
                "set payload_data = ?, created_at = ?, updated_at = ?, metadata = ? "
                "where rowid = ?",
                (
                    row["payload_data"],
                    row["created_at"],
                    row["updated_at"],
                    row["metadata"],
                    int(snapshot.id),
                ),
            )
        return snapshot

    async def clear_pending_tool_use(self, snapshot: PendingToolUseSnapshot) -> None:
        if snapshot.id is None:
            return
        with self.db.conn:
            self.db.conn.execute(
                f"delete from {self.TABLE_NAME} where rowid = ?",
                (int(snapshot.id),),
            )
        snapshot.id = None
