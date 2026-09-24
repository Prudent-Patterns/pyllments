import pytest

from pyllments.elements.llm_chat import CloudflareAIGatewayChatModel, LLMChatElement
from pyllments.payloads.message import MessagePayload


def _user_message(content: str = "Hello") -> MessagePayload:
    return MessagePayload(role="user", content=content)


def _cloudflare_model(**kwargs) -> CloudflareAIGatewayChatModel:
    defaults = {
        "account_id": "acct-123",
        "api_key": "token-123",
        "gateway_id": "default",
        "model_name": "openai/gpt-4.1-mini",
    }
    defaults.update(kwargs)
    return CloudflareAIGatewayChatModel(**defaults)


@pytest.mark.asyncio
async def test_cloudflare_atomic_response_posts_completions(monkeypatch):
    recorded = {}

    async def _fake_http_post(self, url, headers, body, *, stream):
        recorded["url"] = url
        recorded["headers"] = headers
        recorded["body"] = body
        recorded["stream"] = stream
        return {
            "choices": [
                {"message": {"content": "gateway-atomic", "tool_calls": []}}
            ]
        }

    monkeypatch.setattr(CloudflareAIGatewayChatModel, "_http_post", _fake_http_post)
    model = _cloudflare_model(
        output_mode="atomic",
        model_args={"temperature": 0.2},
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "ping"}}],
        gateway_headers={"cf-aig-skip-cache": "true"},
    )

    response_payload = model.generate_response([_user_message("ping")])
    assert response_payload.model.mode == "atomic"
    response = await response_payload.model.message_coroutine

    assert response.choices[0].message.content == "gateway-atomic"
    assert recorded["stream"] is False
    assert recorded["url"].endswith("/accounts/acct-123/ai/v1/chat/completions")
    assert recorded["headers"]["Authorization"] == "Bearer token-123"
    assert recorded["headers"]["cf-aig-gateway-id"] == "default"
    assert recorded["headers"]["cf-aig-skip-cache"] == "true"
    assert recorded["body"]["model"] == "openai/gpt-4.1-mini"
    assert recorded["body"]["messages"][0]["content"] == "ping"
    assert recorded["body"]["tools"][0]["function"]["name"] == "ping"
    assert recorded["body"]["response_format"]["type"] == "json_object"


@pytest.mark.asyncio
async def test_cloudflare_stream_response_parses_sse_chunks(monkeypatch):
    async def _fake_http_post(self, url, headers, body, *, stream):
        assert stream is True
        assert body["stream"] is True

        async def _chunks():
            yield {"choices": [{"delta": {"content": "Hello"}}]}
            yield {"choices": [{"delta": {"content": " world"}}]}

        return _chunks()

    monkeypatch.setattr(CloudflareAIGatewayChatModel, "_http_post", _fake_http_post)
    model = _cloudflare_model(output_mode="stream")
    response_payload = model.generate_response([_user_message("stream please")])

    assert response_payload.model.mode == "stream"
    chunks = []
    async for event in response_payload.model.message_coroutine:
        chunks.append(event.choices[0].delta.content)
    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_cloudflare_atomic_response_populates_tool_calls(monkeypatch):
    async def _fake_http_post(self, url, headers, body, *, stream):
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(CloudflareAIGatewayChatModel, "_http_post", _fake_http_post)
    model = _cloudflare_model(
        output_mode="atomic",
        tools=[{"type": "function", "function": {"name": "lookup"}}],
    )
    response_payload = model.generate_response([_user_message("tools?")])
    await response_payload.model.aget_message()

    assert response_payload.model.tool_calls
    assert response_payload.model.tool_calls[0]["function"]["name"] == "lookup"


def test_cloudflare_model_requires_credentials(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    model = CloudflareAIGatewayChatModel(model_name="openai/gpt-4.1-mini")

    with pytest.raises(ValueError, match="CLOUDFLARE_API_TOKEN"):
        model._build_request_target()


def test_cloudflare_catalog_groups_workers_ai_models():
    provider_map = CloudflareAIGatewayChatModel.get_provider_model_catalog(
        models=[
            "openai/gpt-4.1-mini",
            "anthropic/claude-sonnet-4",
            "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "workers-ai/@cf/moonshotai/kimi-k2.6",
        ]
    )

    assert provider_map["openai"] == ["openai/gpt-4.1-mini"]
    assert provider_map["workers-ai"] == [
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "@cf/moonshotai/kimi-k2.6",
    ]


def test_llm_chat_element_constructs_cloudflare_backend():
    element = LLMChatElement(
        backend="cloudflare",
        account_id="acct-123",
        api_key="token-123",
    )
    assert isinstance(element.model, CloudflareAIGatewayChatModel)
    assert element.model.account_id == "acct-123"


def test_llm_chat_element_hot_swaps_to_cloudflare():
    element = LLMChatElement(backend="mock")
    element.backend = "cloudflare"
    assert isinstance(element.model, CloudflareAIGatewayChatModel)
