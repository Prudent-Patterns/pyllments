from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    """Normalized tool definition exposed to ToolUseElement."""

    adapter_name: str
    provider_name: str | None
    tool_name: str
    model_tool_name: str
    description: str
    parameters_schema: dict[str, Any]
    permission_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Normalized successful tool execution result."""

    content: list[dict[str, Any]]
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "raw": self.raw,
            "metadata": self.metadata,
        }


@dataclass
class ToolError:
    """Normalized tool execution error."""

    type: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ToolAdapter(Protocol):
    """Backend-facing tool adapter contract."""

    name: str

    async def setup(self) -> None: ...

    async def list_tools(self) -> dict[str, ToolSpec]: ...

    async def call_tool(
        self,
        *,
        provider_name: str | None,
        tool_name: str,
        parameters: dict | None,
    ) -> ToolResult: ...

    async def close(self) -> None: ...
