import importlib

from .llm_chat_element import LLMChatElement

_BACKEND_EXPORTS = {
    "MockChatModel": ".mock_chat_model",
    "OpenRouterChatModel": ".openrouter_chat_model",
    "LiteLLMChatModel": ".litellm_chat_model",
    "CloudflareAIGatewayChatModel": ".cloudflare_ai_gateway_chat_model",
}

__all__ = ["LLMChatElement", *_BACKEND_EXPORTS]


def __getattr__(name):
    if name in _BACKEND_EXPORTS:
        module = importlib.import_module(_BACKEND_EXPORTS[name], __name__)
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
