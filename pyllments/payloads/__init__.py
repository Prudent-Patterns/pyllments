import importlib
from typing import TYPE_CHECKING

# Type hints for IDE support
if TYPE_CHECKING:
    from .message import MessagePayload
    from .chunk import ChunkPayload
    from .file import FilePayload
    from .tools_response import ToolsResponsePayload
    from .schema import SchemaPayload
    from .structured import StructuredPayload

# Define mapping between class names and their module paths
PAYLOAD_MAPPING = {
    "MessagePayload": ".message",
    "ChunkPayload": ".chunk",
    "FilePayload": ".file",
    "ToolListPayload": ".tool_list",
    "ToolCallPayload": ".tool_call",
    "ToolsResponsePayload": ".tools_response",
    "SchemaPayload": ".schema",
    "StructuredPayload": ".structured",
}

def __getattr__(name):
    if name in PAYLOAD_MAPPING:
        module_name = PAYLOAD_MAPPING[name]
        module = importlib.import_module(module_name, __name__)
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    return list(PAYLOAD_MAPPING.keys())