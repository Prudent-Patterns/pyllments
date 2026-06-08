from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import jinja2
import param

from pyllments.base.model_base import Model

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "denied", "cancelled"})
NON_EXECUTABLE_STATUSES = TERMINAL_STATUSES | frozenset({"awaiting_permission", "running"})


def new_tool_use_id() -> str:
    return f"tooluse_{uuid4().hex[:12]}"


def new_payload_id() -> str:
    return f"tup_{uuid4().hex[:12]}"


class ToolUseModel(Model):
    """
    Durable model for one or more tool calls and their lifecycle state.

    Represents the full tool-use lifecycle from model request through permission,
    execution, and result/error attachment without storing executable callables.
    """

    payload_id = param.String(default=None, doc="Stable id for this payload instance")
    turn_id = param.String(default=None, allow_None=True, doc="Application turn id")
    flow_id = param.String(default=None, allow_None=True, doc="Flow identifier for routing")
    flow_version = param.String(default=None, allow_None=True, doc="Flow version for durable routing")
    executor_element_name = param.String(
        default=None,
        allow_None=True,
        doc="Name of the ToolUseElement that executes this payload",
    )
    status = param.String(default="pending", doc="Aggregate lifecycle status")
    tool_uses = param.Dict(default={}, doc="Tool-use records keyed by tool_use_id")
    metadata = param.Dict(default={}, doc="Optional payload-level metadata")
    timestamp = param.Number(default=None, doc="Unix timestamp when the payload was created")
    updated_at = param.Number(default=None, doc="Unix timestamp of the last mutation")
    correlation_id = param.String(
        default=None,
        allow_None=True,
        doc="Optional turn/correlation identifier for gateway matching",
    )
    _content = param.String(default="", doc="Rendered model-facing content string")
    template = param.ClassSelector(default=None, class_=jinja2.Template)
    completed = param.Boolean(default=False, doc="True when all tool uses are terminal")

    def __init__(self, **params):
        super().__init__(**params)
        now = time.time()
        if self.payload_id is None:
            self.payload_id = new_payload_id()
        if self.timestamp is None:
            self.timestamp = now
        if self.updated_at is None:
            self.updated_at = self.timestamp
        if self.correlation_id is None and self.turn_id is not None:
            self.correlation_id = self.turn_id
        self.set_template()
        self._refresh_aggregate_status()

    @property
    def content(self) -> str:
        if not self._content:
            self._content = self.template.render(tool_uses=self.tool_uses)
        return self._content

    def set_template(self):
        self.template = jinja2.Template("""The following tool results are available:
{%- for tool_use_id, record in tool_uses.items() %}
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
{%- endif %}
{%- endfor %}""")

    def _touch(self):
        self.updated_at = time.time()
        self._content = ""
        self._refresh_aggregate_status()

    def _refresh_aggregate_status(self):
        records = list((self.tool_uses or {}).values())
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
            "request_id": None,
            "decided_at": None,
            "decided_by": None,
            "reason": None,
        }

    def add_tool_use(
        self,
        *,
        adapter_name: str,
        tool_name: str,
        model_tool_name: str,
        parameters: dict | None = None,
        provider_name: str | None = None,
        description: str = "",
        permission_required: bool = False,
        tool_use_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Register a proposed tool use and return its stable id."""
        tool_use_id = tool_use_id or new_tool_use_id()
        now = time.time()
        status = "awaiting_permission" if permission_required else "approved"
        permission = self.default_permission(required=permission_required)
        self.tool_uses[tool_use_id] = {
            "tool_use_id": tool_use_id,
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
        self._touch()
        return tool_use_id

    def apply_permission_request(self, request_id: str, tool_use_ids: list[str] | None = None):
        """Mark permission as awaiting with a gateway request id."""
        for tool_use_id, record in self.tool_uses.items():
            if tool_use_ids is not None and tool_use_id not in tool_use_ids:
                continue
            if not record.get("permission_required"):
                continue
            record["permission"]["status"] = "awaiting"
            record["permission"]["request_id"] = request_id
            record["status"] = "awaiting_permission"
            record["updated_at"] = time.time()
        self._touch()

    def approve(self, tool_use_ids: list[str] | None = None, *, decided_by: str | None = None):
        """Approve one or all permission-gated tool uses."""
        now = time.time()
        for tool_use_id, record in self.tool_uses.items():
            if tool_use_ids is not None and tool_use_id not in tool_use_ids:
                continue
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
        tool_use_ids: list[str] | None = None,
        *,
        reason: str | None = None,
        decided_by: str | None = None,
    ):
        """Deny one or all permission-gated tool uses."""
        now = time.time()
        for tool_use_id, record in self.tool_uses.items():
            if tool_use_ids is not None and tool_use_id not in tool_use_ids:
                continue
            if record.get("status") in TERMINAL_STATUSES:
                continue
            record["permission"]["status"] = "denied"
            record["permission"]["decided_at"] = now
            record["permission"]["decided_by"] = decided_by
            record["permission"]["reason"] = reason
            record["status"] = "denied"
            record["updated_at"] = now
        self._touch()

    def can_execute(self, tool_use_id: str) -> bool:
        record = self.tool_uses.get(tool_use_id, {})
        return record.get("status") == "approved"

    def mark_running(self, tool_use_id: str):
        record = self.tool_uses[tool_use_id]
        record["status"] = "running"
        record["updated_at"] = time.time()
        self._touch()

    def attach_result(self, tool_use_id: str, result: dict[str, Any]):
        record = self.tool_uses[tool_use_id]
        record["result"] = result
        record["error"] = None
        record["status"] = "succeeded"
        record["updated_at"] = time.time()
        self._touch()

    def attach_error(self, tool_use_id: str, error: dict[str, Any]):
        record = self.tool_uses[tool_use_id]
        record["error"] = error
        record["status"] = "failed"
        record["updated_at"] = time.time()
        self._touch()

    def recover_stale_running(self):
        """Mark interrupted running calls as failed with retryable=true."""
        for record in self.tool_uses.values():
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
            for record in self.tool_uses.values()
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
