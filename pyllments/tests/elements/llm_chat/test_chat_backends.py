from types import SimpleNamespace

import inspect
import pytest

from pyllments.elements.llm_chat import LLMChatElement, LiteLLMChatModel, OpenRouterChatModel
from pyllments.elements.llm_chat import openrouter_chat_model as openrouter_module
from pyllments.elements.llm_chat import litellm_chat_model as litellm_module
from pyllments.payloads.message import MessagePayload


def _user_message(content: str = "Hello") -> MessagePayload:
    return MessagePayload(role="user", content=content)


class _FakeOpenRouter:
    last_client_kwargs = None
    last_request_kwargs = None

    def __init__(self, **kwargs):
        _FakeOpenRouter.last_client_kwargs = kwargs
        self.chat = SimpleNamespace(send_async=self._send_async)
        self.models = SimpleNamespace(list=self._list_models)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def _send_async(self, **kwargs):
        _FakeOpenRouter.last_request_kwargs = kwargs
        if kwargs.get("stream"):
            async def _stream():
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="chunk", tool_calls=None))]
                )
            return _stream()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="atomic", tool_calls=[]))]
        )

    def _list_models(self):
        return SimpleNamespace(
            data=[
                SimpleNamespace(id="openai/gpt-4o-mini"),
                SimpleNamespace(id="anthropic/claude-3.7-sonnet"),
                SimpleNamespace(id="google/gemini-2.5-pro"),
            ]
        )


@pytest.mark.asyncio
async def test_openrouter_atomic_response_wraps_coroutine(monkeypatch):
    monkeypatch.setattr(openrouter_module, "OpenRouter", _FakeOpenRouter)
    model = OpenRouterChatModel(
        output_mode="atomic",
        model_name="openai/gpt-4o-mini",
        model_args={"temperature": 0.2},
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "ping"}}],
        api_key="test-key",
    )

    response_payload = model.generate_response([_user_message("ping")])

    assert response_payload.model.mode == "atomic"
    response = await response_payload.model.message_coroutine
    assert response.choices[0].message.content == "atomic"
    assert _FakeOpenRouter.last_client_kwargs["api_key"] == "test-key"
    assert _FakeOpenRouter.last_request_kwargs["stream"] is False
    assert _FakeOpenRouter.last_request_kwargs["tools"][0]["function"]["name"] == "ping"
    assert _FakeOpenRouter.last_request_kwargs["response_format"]["type"] == "json_object"


@pytest.mark.asyncio
async def test_openrouter_stream_response_wraps_async_iterator(monkeypatch):
    monkeypatch.setattr(openrouter_module, "OpenRouter", _FakeOpenRouter)
    model = OpenRouterChatModel(
        output_mode="stream",
        model_name="openai/gpt-4o-mini",
    )

    response_payload = model.generate_response([_user_message("stream please")])

    assert response_payload.model.mode == "stream"
    chunks = []
    async for event in response_payload.model.message_coroutine:
        chunks.append(event.choices[0].delta.content)
    assert chunks == ["chunk"]
    assert _FakeOpenRouter.last_request_kwargs["stream"] is True


def test_openrouter_model_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(openrouter_module, "load_dotenv", lambda *args, **kwargs: None)
    model = OpenRouterChatModel(model_name="openai/gpt-4o-mini")

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        model._build_client_kwargs()


@pytest.mark.asyncio
async def test_litellm_stream_response_keeps_existing_contract(monkeypatch):
    recorded = {}

    async def _fake_acompletion(**kwargs):
        recorded.update(kwargs)
        if kwargs.get("stream"):
            async def _stream():
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="lite", tool_calls=None))]
                )
            return _stream()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="lite-atomic", tool_calls=[]))]
        )

    monkeypatch.setattr(litellm_module.litellm, "acompletion", _fake_acompletion)
    model = LiteLLMChatModel(
        output_mode="stream",
        model_name="gpt-4o-mini",
        model_args={"temperature": 0.1},
        tools=[{"type": "function", "function": {"name": "echo"}}],
    )

    response_payload = model.generate_response([_user_message("hello")])
    assert response_payload.model.mode == "stream"
    stream_source = response_payload.model.message_coroutine
    if inspect.isawaitable(stream_source) and not hasattr(stream_source, "__aiter__"):
        stream_source = await stream_source
    async for _ in stream_source:
        break
    assert recorded["stream"] is True
    assert recorded["tools"][0]["function"]["name"] == "echo"


def test_llm_chat_element_defaults_to_openrouter():
    element = LLMChatElement()
    assert isinstance(element.model, OpenRouterChatModel)


def test_llm_chat_element_hot_swaps_backend():
    element = LLMChatElement()
    element.backend = "litellm"
    assert isinstance(element.model, LiteLLMChatModel)


def test_openrouter_model_selector_groups_models_by_provider():
    element = LLMChatElement(backend="openrouter")
    selector_view = element.create_model_selector_view(
        models=[
            "openai/gpt-4o-mini",
            "openai/gpt-4.1-mini",
            "anthropic/claude-3.7-sonnet",
            "google/gemini-2.5-pro",
            "x-ai/grok-3-mini",
        ],
        show_provider_selector=True,
    )

    provider_selector = selector_view[0]
    model_selector = selector_view[2]

    assert len(provider_selector.options) <= 6
    assert "OpenAI" in provider_selector.options
    assert provider_selector.value == "openai"

    provider_selector.value = "anthropic"
    assert all(
        cfg["model"].startswith("anthropic/")
        for cfg in model_selector.options.values()
    )


def test_openrouter_selector_uses_model_catalog(monkeypatch):
    element = LLMChatElement(backend="openrouter")
    called = {"count": 0}

    def _fake_catalog(models=None, max_providers=6):
        called["count"] += 1
        return {"openai": ["openai/gpt-4o-mini"]}

    monkeypatch.setattr(type(element.model), "get_provider_model_catalog", classmethod(lambda cls, models=None, max_providers=6: _fake_catalog(models=models, max_providers=max_providers)))
    element.create_model_selector_view(show_provider_selector=True)
    assert called["count"] == 1


def test_openrouter_selector_with_empty_models_falls_back_to_builtin_catalog():
    element = LLMChatElement(backend="openrouter")
    type(element.model)._fetch_available_model_ids = classmethod(
        lambda cls: [
            "openai/gpt-4o-mini",
            "anthropic/claude-3.7-sonnet",
            "google/gemini-2.5-pro",
        ]
    )
    selector_view = element.create_model_selector_view(
        models={},
        model="openai/gpt-4o-mini",
        show_provider_selector=True,
    )

    provider_selector = selector_view[0]
    model_selector = selector_view[2]

    assert provider_selector.value != "default"
    assert len(provider_selector.options) > 0
    assert len(model_selector.options) > 0


def test_openrouter_catalog_fetch_falls_back_without_litellm(monkeypatch):
    class _BrokenOpenRouter:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            raise RuntimeError("boom")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(openrouter_module, "OpenRouter", _BrokenOpenRouter)

    provider_map = OpenRouterChatModel.get_provider_model_catalog(models=None)

    assert "openai" in provider_map
    assert all("/" in model_name for models in provider_map.values() for model_name in models)


def test_openrouter_catalog_fetch_uses_python_sdk(monkeypatch):
    monkeypatch.setattr(openrouter_module, "OpenRouter", _FakeOpenRouter)

    model_ids = OpenRouterChatModel._fetch_available_model_ids()

    assert "openai/gpt-4o-mini" in model_ids
    assert "anthropic/claude-3.7-sonnet" in model_ids
