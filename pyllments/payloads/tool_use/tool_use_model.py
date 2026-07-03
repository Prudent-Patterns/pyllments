from __future__ import annotations

import asyncio
import time
from typing import Any

import jinja2
import param

from pyllments.base.model_base import Model

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "denied", "cancelled", "orphaned_completed"})
NON_EXECUTABLE_STATUSES = TERMINAL_STATUSES | frozenset(
    {"awaiting_permission", "running", "cancel_requested"}
)


class ToolUseModel(Model):
    """
    Durable model for one or more tool calls and their lifecycle state.

    Represents the full tool-use lifecycle from model request through permission,
    execution, and result/error attachment without storing executable callables.
    """

    flow_id = param.String(
        default=None,
        allow_None=True,
        doc="Optional application-level flow identifier (not used for executor rebinding)",
    )
    flow_version = param.String(
        default=None,
        allow_None=True,
        doc="Optional application-level flow version (not used for executor rebinding)",
    )
    executor_element_name = param.String(
        default=None,
        allow_None=True,
        doc="Name of the ToolUseElement that executes this payload",
    )
    status = param.String(default="pending", doc="Aggregate lifecycle status")
    tool_calls = param.List(default=[], item_type=dict, doc="Ordered tool-call records")
    metadata = param.Dict(default={}, doc="Optional payload-level metadata")
    timestamp = param.Number(default=None, doc="Unix timestamp when the payload was created")
    updated_at = param.Number(default=None, doc="Unix timestamp of the last mutation")
    _content = param.String(default="", doc="Rendered model-facing content string")
    template = param.ClassSelector(default=None, class_=jinja2.Template)
    completed = param.Boolean(default=False, doc="True when all tool calls are terminal")

    def __init__(self, **params):
        super().__init__(**params)
        now = time.time()
        if self.timestamp is None:
            self.timestamp = now
        if self.updated_at is None:
            self.updated_at = self.timestamp
        self.set_template()
        self._refresh_aggregate_status()

    @property
    def content(self) -> str:
        if not self._content:
            self._content = self.template.render(tool_calls=self.tool_calls)
        return self._content

    def set_template(self):
        self.template = jinja2.Template("""The following tool results are available:
{%- for record in tool_calls %}
{%- if record.status == 'succeeded' and record.result %}
### Tool: {{ record.model_tool_name }}
{%- if record.parameters %}
Parameters:
{%- for param_name, param_value in record.parameters.items() %}
- {{ param_name }}: {{ param_value }}
{%- endfor %}
{%- endif %}
Result:
{%- for item in record.result.content %}
{{ item.text }}
{%- endfor %}
{%- elif record.status == 'failed' and record.error %}
### Tool: {{ record.model_tool_name }} failed
{{ record.error.message }}
{%- elif record.status == 'denied' %}
### Tool: {{ record.model_tool_name }} denied
{%- if record.permission and record.permission.reason %}
Reason: {{ record.permission.reason }}
{%- endif %}
{%- elif record.status == 'cancelled' %}
### Tool: {{ record.model_tool_name }} cancelled
{%- if record.error and record.error.message %}
{{ record.error.message }}
{%- endif %}
{%- endif %}
{%- endfor %}""")

    def _touch(self):
        self.updated_at = time.time()
        self._content = ""
        self._refresh_aggregate_status()

    def _refresh_aggregate_status(self):
        records = list(self.tool_calls or [])
        if not records:
            self.status = "pending"
            self.completed = False
            return

        statuses = {record.get("status", "proposed") for record in records}
        if statuses <= TERMINAL_STATUSES:
            self.status = "completed"
            self.completed = True
            return

        self.completed = False
        if "running" in statuses:
            self.status = "running"
        elif "cancel_requested" in statuses:
            self.status = "cancel_requested"
        elif "awaiting_permission" in statuses:
            self.status = "awaiting_permission"
        elif "approved" in statuses:
            self.status = "approved"
        elif "cancelled" in statuses:
            self.status = "cancelled"
        else:
            self.status = "pending"

    @staticmethod
    def default_permission(*, required: bool) -> dict[str, Any]:
        return {
            "status": "awaiting" if required else "not_required",
            "decided_at": None,
            "decided_by": None,
            "reason": None,
        }

    def _iter_indices(self, indices: list[int] | None = None):
        if indices is None:
            yield from range(len(self.tool_calls))
            return
        for index in indices:
            if 0 <= index < len(self.tool_calls):
                yield index

    def add_tool_call(
        self,
        *,
        adapter_name: str,
        tool_name: str,
        model_tool_name: str,
        parameters: dict | None = None,
        provider_name: str | None = None,
        description: str = "",
        permission_required: bool = False,
        metadata: dict | None = None,
    ) -> int:
        """Register a proposed tool call and return its list index."""
        now = time.time()
        status = "awaiting_permission" if permission_required else "approved"
        permission = self.default_permission(required=permission_required)
        record = {
            "adapter_name": adapter_name,
            "provider_name": provider_name,
            "tool_name": tool_name,
            "model_tool_name": model_tool_name,
            "description": description,
            "parameters": parameters or {},
            "permission_required": permission_required,
            "permission": permission,
            "status": status,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }
        self.tool_calls = [*self.tool_calls, record]
        self._touch()
        return len(self.tool_calls) - 1

    def apply_permission_request(self, indices: list[int] | None = None):
        """Mark permission-gated tool calls as awaiting an application decision."""
        for index in self._iter_indices(indices):
            record = self.tool_calls[index]
            if not record.get("permission_required"):
                continue
            record["permission"]["status"] = "awaiting"
            record["status"] = "awaiting_permission"
            record["updated_at"] = time.time()
        self._touch()

    def approve(self, indices: list[int] | None = None, *, decided_by: str | None = None):
        """Approve one or all permission-gated tool calls."""
        now = time.time()
        for index in self._iter_indices(indices):
            record = self.tool_calls[index]
            if record.get("status") not in {"awaiting_permission", "proposed"}:
                continue
            record["permission"]["status"] = "approved"
            record["permission"]["decided_at"] = now
            record["permission"]["decided_by"] = decided_by
            record["status"] = "approved"
            record["updated_at"] = now
        self._touch()

    def deny(
        self,
        indices: list[int] | None = None,
        *,
        reason: str | None = None,
        decided_by: str | None = None,
    ):
        """Deny one or all permission-gated tool calls."""
        now = time.time()
        for index in self._iter_indices(indices):
            record = self.tool_calls[index]
            if record.get("status") in TERMINAL_STATUSES:
                continue
            record["permission"]["status"] = "denied"
            record["permission"]["decided_at"] = now
            record["permission"]["decided_by"] = decided_by
            record["permission"]["reason"] = reason
            record["status"] = "denied"
            record["updated_at"] = now
        self._touch()

    def can_execute(self, index: int) -> bool:
        if index < 0 or index >= len(self.tool_calls):
            return False
        return self.tool_calls[index].get("status") == "approved"

    def mark_running(self, index: int):
        record = self.tool_calls[index]
        record["status"] = "running"
        record["updated_at"] = time.time()
        self._touch()

    def attach_result(
        self,
        index: int,
        result: dict[str, Any],
        *,
        orphaned: bool = False,
    ):
        record = self.tool_calls[index]
        record["result"] = result
        record["error"] = None
        record["status"] = "orphaned_completed" if orphaned else "succeeded"
        if orphaned:
            record["metadata"]["orphaned"] = True
        record["updated_at"] = time.time()
        self._touch()

    def attach_error(
        self,
        index: int,
        error: dict[str, Any],
        *,
        orphaned: bool = False,
    ):
        record = self.tool_calls[index]
        record["error"] = error
        record["status"] = "failed"
        if orphaned:
            record["metadata"]["orphaned"] = True
        record["updated_at"] = time.time()
        self._touch()

    def mark_cancel_requested(self, index: int):
        """Mark a tool call as awaiting cooperative cancellation."""
        record = self.tool_calls[index]
        if record.get("status") in TERMINAL_STATUSES:
            return
        record["status"] = "cancel_requested"
        record["updated_at"] = time.time()
        self._touch()

    def mark_cancelled(self, index: int, *, reason: str | None = None):
        """Mark a tool call as cancelled with an optional reason."""
        record = self.tool_calls[index]
        record["status"] = "cancelled"
        record["error"] = {
            "type": "ToolCancelled",
            "message": reason or "Tool invocation was cancelled",
            "retryable": False,
            "details": {},
        }
        record["updated_at"] = time.time()
        self._touch()

    def cancel_call(self, index: int, *, reason: str | None = None):
        """Cancel one non-terminal tool call."""
        if index < 0 or index >= len(self.tool_calls):
            return
        record = self.tool_calls[index]
        if record.get("status") in TERMINAL_STATUSES:
            return
        if record.get("status") == "running":
            self.mark_cancel_requested(index)
            return
        self.mark_cancelled(index, reason=reason)

    def cancel_non_terminal_calls(
        self,
        indices: list[int] | None = None,
        *,
        reason: str | None = None,
    ):
        """Cancel all non-terminal tool calls in the selected subset."""
        for index in self._iter_indices(indices):
            self.cancel_call(index, reason=reason)

    def recover_stale_running(self):
        """Mark interrupted running calls as failed with retryable=true."""
        for record in self.tool_calls:
            if record.get("status") == "running":
                record["status"] = "failed"
                record["error"] = {
                    "type": "ToolExecutionError",
                    "message": "Tool execution interrupted before completion",
                    "retryable": True,
                    "details": {},
                }
                record["updated_at"] = time.time()
        self._touch()

    def pending_permission_tool_names(self) -> list[str]:
        return [
            record["model_tool_name"]
            for record in self.tool_calls
            if record.get("permission_required")
            and record.get("status") == "awaiting_permission"
        ]

    def pending_permission_indices(self) -> list[int]:
        """Return list indices for tool calls still awaiting permission."""
        return [
            index
            for index, record in enumerate(self.tool_calls)
            if record.get("permission_required")
            and record.get("status") == "awaiting_permission"
        ]

    def needs_permission(self) -> bool:
        return bool(self.pending_permission_tool_names())

    async def await_ready(self):
        """Await until all tool uses are terminal."""
        if self.completed:
            return self
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def _on_completed(event):
            if event.new:
                future.set_result(self)
                self.param.unwatch(_watcher)

        _watcher = self.param.watch(_on_completed, "completed")
        await future
        return self
