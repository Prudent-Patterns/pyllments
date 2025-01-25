import importlib
from typing import TYPE_CHECKING


# Type hints for IDE support
if TYPE_CHECKING:
    from .chat_interface import ChatInterfaceElement
    from .file_loader import FileLoaderElement
    from .embedder import EmbedderElement
    from .retriever import RetrieverElement
    from .llm_chat import LLMChatElement
    from .history_handler import HistoryHandlerElement
    from .chunker import TextChunkerElement
    from .api import APIElement
    from .context_builder import ContextBuilder
    
# Define mapping between class names and their module paths
ELEMENT_MAPPING = {
    "ChatInterfaceElement": ".chat_interface",
    "FileLoaderElement": ".file_loader",
    "EmbedderElement": ".embedder",
    "RetrieverElement": ".retriever",
    "LLMChatElement": ".llm_chat",
    "HistoryHandlerElement": ".history_handler",
    "TextChunkerElement": ".chunker",
    "APIElement": ".api",
    "ContextBuilder": ".context_builder"
}

def __getattr__(name):
    if name in ELEMENT_MAPPING:
        module_name = ELEMENT_MAPPING[name]
        module = importlib.import_module(module_name, __name__)
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

def __dir__():
    return list(ELEMENT_MAPPING.keys())
