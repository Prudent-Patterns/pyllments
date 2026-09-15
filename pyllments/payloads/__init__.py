import importlib
from typing import TYPE_CHECKING

# Type hints for IDE support
if TYPE_CHECKING:
    from .message import MessagePayload
    from .chunk import ChunkPayload
    from .file import FilePayload
    from .tool_use import ToolUsePayload
    from .schema import SchemaPayload
    from .structured import StructuredPayload

# Define mapping between class names and their module paths
PAYLOAD_MAPPING = {
    "MessagePayload": ".message",
    "ChunkPayload": ".chunk",
    "FilePayload": ".file",
    "ToolUsePayload": ".tool_use",
    "SchemaPayload": ".schema",
    "StructuredPayload": ".structured",
}

# Submodule names so PEP 562 does not hide payloads.schema (and friends)
# when Pyodide does getattr(package, "schema") during a relative import.
_PAYLOAD_SUBMODULES = frozenset(PAYLOAD_MAPPING.values())


def __getattr__(name):
    if name in PAYLOAD_MAPPING:
        module = importlib.import_module(PAYLOAD_MAPPING[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    if f".{name}" in _PAYLOAD_SUBMODULES:
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    return list(PAYLOAD_MAPPING.keys())
