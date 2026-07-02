from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyllments.payloads import ToolUsePayload


@dataclass
class ToolCallHandle:
    """Application-facing handle for one tool-call record."""

    payload: ToolUsePayload
    index: int

    @property
    def record(self) -> dict[str, Any]:
        """Return the underlying mutable tool-call record."""
        return self.payload.model.tool_calls[self.index]

    @property
    def name(self) -> str | None:
        return self.record.get("model_tool_name")

    @property
    def adapter_name(self) -> str | None:
        return self.record.get("adapter_name")

    @property
    def provider_name(self) -> str | None:
        return self.record.get("provider_name")

    @property
    def tool_name(self) -> str | None:
        return self.record.get("tool_name")

    @property
    def description(self) -> str:
        return self.record.get("description", "")

    @property
    def parameters(self) -> dict:
        return self.record.get("parameters", {})

    @property
    def status(self) -> str | None:
        return self.record.get("status")

    @property
    def permission(self) -> dict:
        return self.record.get("permission", {})

    @property
    def permission_required(self) -> bool:
        return bool(self.record.get("permission_required"))

    @property
    def needs_permission(self) -> bool:
        return self.permission_required and self.status == "awaiting_permission"

    @property
    def result(self) -> dict | None:
        return self.record.get("result")

    @property
    def error(self) -> dict | None:
        return self.record.get("error")

    def approve(self, *, decided_by: str | None = None) -> None:
        """Approve this tool call for execution."""
        self.payload.model.approve([self.index], decided_by=decided_by)

    def deny(
        self,
        reason: str | None = None,
        *,
        decided_by: str | None = None,
    ) -> None:
        """Deny this tool call and record the optional reason."""
        self.payload.model.deny([self.index], reason=reason, decided_by=decided_by)


@dataclass
class ToolUseNotice:
    """Application-facing notification for every tool call in a payload."""

    payload: ToolUsePayload
    tools: list[ToolCallHandle]

    @classmethod
    def from_payload(cls, payload: ToolUsePayload) -> ToolUseNotice:
        """Build handles for every tool call in order."""
        return cls(
            payload=payload,
            tools=[
                ToolCallHandle(payload=payload, index=index)
                for index in range(len(payload.model.tool_calls))
            ],
        )

    @property
    def permission_tools(self) -> list[ToolCallHandle]:
        """Return tools currently waiting for an application decision."""
        return [tool for tool in self.tools if tool.needs_permission]


@dataclass
class ToolPermissionRequest:
    """Application-facing request for tool calls requiring a decision."""

    payload: ToolUsePayload
    tools: list[ToolCallHandle]

    @classmethod
    def from_payload(cls, payload: ToolUsePayload) -> ToolPermissionRequest:
        """Build a request containing only calls awaiting permission."""
        notice = ToolUseNotice.from_payload(payload)
        return cls(payload=payload, tools=notice.permission_tools)

    @property
    def pending_tools(self) -> list[ToolCallHandle]:
        """Return tools still awaiting approval or denial."""
        return [tool for tool in self.tools if tool.needs_permission]

    @property
    def approved_tools(self) -> list[ToolCallHandle]:
        return [tool for tool in self.tools if tool.status == "approved"]

    @property
    def denied_tools(self) -> list[ToolCallHandle]:
        return [tool for tool in self.tools if tool.status == "denied"]

    @property
    def has_decisions(self) -> bool:
        return bool(self.approved_tools or self.denied_tools)

    @property
    def is_complete(self) -> bool:
        return not self.pending_tools

    def approve_all(self, *, decided_by: str | None = None) -> None:
        """Approve every still-pending tool in this request."""
        for tool in self.pending_tools:
            tool.approve(decided_by=decided_by)

    def deny_all(
        self,
        reason: str | None = None,
        *,
        decided_by: str | None = None,
    ) -> None:
        """Deny every still-pending tool in this request."""
        for tool in self.pending_tools:
            tool.deny(reason=reason, decided_by=decided_by)
