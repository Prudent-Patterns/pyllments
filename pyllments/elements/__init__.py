import importlib

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
