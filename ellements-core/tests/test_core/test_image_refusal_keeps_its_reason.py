"""A refused image call keeps the provider's reason and retry guidance, never its message."""

import httpx
import openai
import pytest
from ellements.core.llm.image_transport import (
    ImageGenerationTransportError,
    OpenAIImageGenerationTransport,
)

REQUEST = {
    "model": "openai/gpt-image-2", "prompt": "Synthetic", "size": "1024x1024",
    "quality": "high", "n": 1, "output_format": "png", "background": "opaque",
}
#: Captured once: a test that refuses twice must not wrap its own stand-in.
ACTUAL_CLIENT = openai.AsyncOpenAI


async def _refusal(monkeypatch, status, headers, error):
    def respond(request):
        return httpx.Response(
            status, headers={"x-request-id": "req-refused", **headers}, json={"error": error},
        )

    def client(**kwargs):
        return ACTUAL_CLIENT(
            **kwargs, api_key="synthetic-not-a-secret",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        )

    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    with pytest.raises(ImageGenerationTransportError) as caught:
        await OpenAIImageGenerationTransport(timeout_seconds=60).generate(REQUEST)
    return caught.value.diagnostic


@pytest.mark.asyncio
async def test_an_empty_account_is_told_apart_from_a_brief_limit(monkeypatch):
    empty = await _refusal(monkeypatch, 429, {"retry-after": "60"}, {
        "message": "You exceeded your quota; private prompt text",
        "type": "insufficient_quota", "code": "insufficient_quota",
    })
    brief = await _refusal(monkeypatch, 429, {"retry-after-ms": "1500"}, {
        "message": "Rate limit reached for private-org", "type": "requests",
        "code": "rate_limit_exceeded",
    })

    assert empty["http_status"] == brief["http_status"] == 429
    assert empty["provider_error_code"] == "insufficient_quota"
    assert empty["retry_after_seconds"] == 60
    assert brief["provider_error_code"] == "rate_limit_exceeded"
    assert brief["provider_error_type"] == "requests"
    assert brief["retry_after_seconds"] == 1.5
    assert "private" not in repr(empty) + repr(brief)


@pytest.mark.asyncio
async def test_anything_but_a_plain_word_or_bounded_number_is_dropped(monkeypatch):
    diagnostic = await _refusal(monkeypatch, 429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, {
        "message": "private", "type": "Insufficient Quota: sk-private", "code": "x" * 200,
    })
    assert "provider_error_code" not in diagnostic
    assert "provider_error_type" not in diagnostic
    assert "retry_after_seconds" not in diagnostic

    far = await _refusal(monkeypatch, 429, {"retry-after": "999999"}, {"code": "insufficient_quota"})
    assert far["provider_error_code"] == "insufficient_quota"
    assert "retry_after_seconds" not in far
