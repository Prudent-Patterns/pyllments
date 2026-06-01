from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, List, Optional, Union

import param

from pyllments.base.model_base import Model
from pyllments.payloads import MessagePayload, ToolsResponsePayload
from pyllments.runtime.loop_registry import LoopRegistry

from .history_projection import (
    HistoryEntry,
    ProjectionContext,
    TierInterval,
    normalize_projection_tiers,
    payload_token_count,
    project_payload,
    resolve_tier_interval,
)
from .history_store import (
    HistoryRecord,
    HistoryStore,
    SQLiteHistoryStore,
    new_entry_id,
    payload_to_record,
    record_to_payload,
)

SupportedPayload = Union[MessagePayload, ToolsResponsePayload]


class HistoryHandlerModel(Model):
    """
    Raw history ledger with token-tiered projection for context emission.

    Stores original payloads in ``history``. Context and summarization candidates are
    derived at emit time. Optional persistence uses a pluggable HistoryStore.
    """

    history_token_limit = param.Integer(
        default=32000,
        bounds=(1, None),
        doc="Max raw tokens retained in the history ledger.",
    )
    history = param.ClassSelector(class_=deque, default=deque())
    history_token_count = param.Integer(default=0, bounds=(0, None))

    context_token_limit = param.Integer(
        default=16000,
        bounds=(0, None),
        doc="Max projected tokens emitted on context_output.",
    )
    projection_tiers = param.Dict(
        default=None,
        allow_None=True,
        doc="Numeric tier boundaries -> {payload_type: projector}.",
    )
    summary_token_threshold = param.Integer(
        default=8000,
        bounds=(0, None),
        doc="Raw entries older than this token distance from newest are eligible for summarization.",
    )

    tokenizer_model = param.String(default="gpt-4o")

    persist = param.Boolean(default=False)
    db_path = param.String(default=None)

    def __init__(self, history_store: Optional[HistoryStore] = None, **params):
        super().__init__(**params)
        self._tier_intervals: List[TierInterval] = normalize_projection_tiers(
            self.projection_tiers,
            self.context_token_limit,
        )
        self._last_summary_candidate_entry_ids: List[str] = []

        self._history_store: Optional[HistoryStore] = history_store
        if self.persist and self._history_store is None:
            self._history_store = SQLiteHistoryStore(db_path=self.db_path, name=self.name)

        self._pending_delete_ids: List[str] = []
        self._pending_append_records: List[HistoryRecord] = []
        self._store_load_task = None

        if self._history_store is not None:
            self._store_load_task = self._schedule_task(self.hydrate_from_store())

    @staticmethod
    def _schedule_task(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = LoopRegistry.get_loop()
        return loop.create_task(coro)

    def _refresh_tier_intervals(self):
        self._tier_intervals = normalize_projection_tiers(
            self.projection_tiers,
            self.context_token_limit,
        )

    @param.depends("projection_tiers", "context_token_limit", watch=True)
    def _on_projection_config_changed(self):
        self._refresh_tier_intervals()

    async def hydrate_from_store(self):
        """Load persisted raw records into memory without projection work."""
        if self._history_store is None:
            return
        for record in await self._history_store.load_records():
            payload = record_to_payload(record)
            if payload is None:
                continue
            entry = HistoryEntry(
                payload=payload,
                raw_token_count=record.raw_token_count,
                timestamp=record.timestamp,
                entry_id=record.entry_id,
                summarized=record.summarized,
                metadata=record.metadata,
            )
            self._append_to_memory(entry, persist=False)

    async def await_store_ready(self):
        """Wait for any scheduled startup hydration to complete."""
        if self._store_load_task is not None:
            await self._store_load_task

    def _wrap_payload(self, payload: SupportedPayload) -> Optional[HistoryEntry]:
        if isinstance(payload, ToolsResponsePayload) and not payload.model.tool_responses:
            return None
        raw_tokens = payload_token_count(payload, self.tokenizer_model)
        if raw_tokens == 0 and isinstance(payload, ToolsResponsePayload):
            return None
        ts = float(payload.model.timestamp)
        return HistoryEntry(
            payload=payload,
            raw_token_count=raw_tokens,
            timestamp=ts,
            entry_id=new_entry_id(),
        )

    def _append_to_memory(self, entry: HistoryEntry, persist: bool = True):
        if entry.raw_token_count > self.history_token_limit:
            raise ValueError(
                f"Token count ({entry.raw_token_count}) exceeds history limit "
                f"({self.history_token_limit})."
            )

        deleted_entries: List[HistoryEntry] = []
        while self.history_token_count + entry.raw_token_count > self.history_token_limit:
            popped = self.history.popleft()
            self.history_token_count -= popped.raw_token_count
            deleted_entries.append(popped)

        self.history.append(entry)
        self.history_token_count += entry.raw_token_count

        if persist and self._history_store is not None:
            for deleted in deleted_entries:
                self._pending_delete_ids.append(deleted.entry_id)
            record = payload_to_record(
                entry.entry_id,
                entry.payload,
                entry.raw_token_count,
                entry.summarized,
            )
            if record is not None:
                self._pending_append_records.append(record)
            self._schedule_task(self._sync_store())

    def _drain_pending_store_ops(self) -> tuple[List[str], List[HistoryRecord]]:
        delete_ids = self._pending_delete_ids.copy()
        append_records = self._pending_append_records.copy()
        self._pending_delete_ids.clear()
        self._pending_append_records.clear()
        return delete_ids, append_records

    async def _apply_store_ops(self, delete_ids: List[str], append_records: List[HistoryRecord]) -> None:
        if not self._history_store:
            return
        if append_records:
            await self._history_store.append_records(append_records)
        if delete_ids:
            await self._history_store.delete_records(delete_ids)

    async def flush_store(self):
        """Apply pending store writes on the current event loop."""
        delete_ids, append_records = self._drain_pending_store_ops()
        await self._apply_store_ops(delete_ids, append_records)

    async def _sync_store(self):
        if not self._history_store:
            return
        delete_ids, append_records = self._drain_pending_store_ops()
        if not delete_ids and not append_records:
            return

        try:
            await self._apply_store_ops(delete_ids, append_records)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error syncing history store: {e}")

    def update_history(self, entry: HistoryEntry):
        self._append_to_memory(entry, persist=True)

    def load_entries(self, entries: List[SupportedPayload]):
        for payload in entries:
            wrapped = self._wrap_payload(payload)
            if wrapped is not None:
                self.update_history(wrapped)
        self.param.trigger("history")

    def load_message(self, message: MessagePayload):
        self.load_entries([message])

    def load_tool_response(self, tool_response: ToolsResponsePayload):
        self.load_entries([tool_response])

    def mark_summary_candidates_summarized(self, entry_ids: List[str]):
        """Mark raw ledger entries covered by an accepted summary artifact."""
        id_set = set(entry_ids)
        for entry in self.history:
            if entry.entry_id in id_set:
                entry.summarized = True
        if self._history_store is not None and entry_ids:
            self._schedule_task(self._mark_summarized_async(entry_ids))

    async def _mark_summarized_async(self, entry_ids: List[str]):
        if self._history_store is None:
            return
        try:
            await self._history_store.mark_summarized(entry_ids)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error marking summarized records: {e}")

    def _entries_newest_first(self) -> List[HistoryEntry]:
        return list(reversed(self.history))

    def _project_entry(
        self,
        entry: HistoryEntry,
        token_distance: int,
        entry_index: int,
        remaining_budget: Optional[int],
    ) -> tuple[Any, int]:
        interval = resolve_tier_interval(token_distance, self._tier_intervals)
        ctx = ProjectionContext(
            tier_start=interval.start,
            tier_end=interval.end,
            token_distance_from_newest=token_distance,
            entry_index=entry_index,
            tokenizer_model=self.tokenizer_model,
            remaining_context_budget=remaining_budget,
        )
        projected = project_payload(entry.payload, interval, ctx)
        projected_tokens = payload_token_count(projected, self.tokenizer_model)
        return projected, projected_tokens

    def _select_context_entries(self) -> List[tuple[HistoryEntry, Any]]:
        if not self.history or self.context_token_limit <= 0:
            return []

        selected: List[tuple[HistoryEntry, Any]] = []
        cumulative_distance = 0
        projected_total = 0

        for entry_index, entry in enumerate(self._entries_newest_first()):
            distance = cumulative_distance
            remaining = self.context_token_limit - projected_total
            projected, projected_tokens = self._project_entry(
                entry, distance, entry_index, remaining
            )

            if selected and projected_total + projected_tokens > self.context_token_limit:
                break
            if not selected and projected_tokens > self.context_token_limit:
                selected.append((entry, projected))
                break

            selected.append((entry, projected))
            projected_total += projected_tokens
            cumulative_distance += entry.raw_token_count

        selected.reverse()
        return selected

    def get_context_payloads(self) -> List[Any]:
        return [projected for _, projected in self._select_context_entries()]

    def get_summary_candidate_payloads(self) -> List[Any]:
        if not self.history or self.summary_token_threshold <= 0:
            return []

        entries_chronological = list(self.history)
        cumulative_from_newest = 0
        distances: List[int] = [0] * len(entries_chronological)

        for i in range(len(entries_chronological) - 1, -1, -1):
            distances[i] = cumulative_from_newest
            cumulative_from_newest += entries_chronological[i].raw_token_count

        candidates: List[Any] = []
        candidate_entry_ids: List[str] = []
        for entry, distance in zip(entries_chronological, distances):
            if distance >= self.summary_token_threshold and not entry.summarized:
                candidates.append(entry.payload)
                candidate_entry_ids.append(entry.entry_id)

        if candidates:
            self._last_summary_candidate_entry_ids = candidate_entry_ids
        return candidates

    def accept_summary_artifact(self, artifact: Any):
        import time

        if self._is_supported_payload(artifact):
            wrapped = self._wrap_payload(artifact)
        elif hasattr(artifact, "model"):
            ts = getattr(artifact.model, "timestamp", None) or time.time()
            wrapped = HistoryEntry(
                payload=artifact,
                raw_token_count=max(1, payload_token_count(artifact, self.tokenizer_model)),
                timestamp=float(ts),
                entry_id=new_entry_id(),
            )
        else:
            wrapped = None

        if wrapped is not None:
            self.update_history(wrapped)
        if self._last_summary_candidate_entry_ids:
            self.mark_summary_candidates_summarized(self._last_summary_candidate_entry_ids)
            self._last_summary_candidate_entry_ids = []
        self.param.trigger("history")

    @staticmethod
    def _is_supported_payload(payload: Any) -> bool:
        return isinstance(payload, (MessagePayload, ToolsResponsePayload))

    def get_context_entries_for_view(self) -> List[HistoryEntry]:
        return [entry for entry, _ in self._select_context_entries()]
