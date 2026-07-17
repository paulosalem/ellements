"""Shared LiteLLM request normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import litellm

from .model_params import filter_parameters, get_unsupported_parameters


@dataclass(frozen=True)
class CompletionRequest:
    """Normalized chat-completion request settings."""

    model: str
    params: dict[str, Any]
    logged_max_tokens: int | None


def configure_litellm_globals(config: Mapping[str, Any]) -> None:
    """Apply top-level LiteLLM configuration from a client config mapping."""
    if "api_key" in config:
        litellm.api_key = config["api_key"]
    if "base_url" in config:
        litellm.api_base = config["base_url"]


def resolve_model_name(
    model: str,
    *,
    use_responses_api: bool = False,
) -> tuple[str, bool]:
    """Resolve provider-prefixed model names for special GPT-5 routing."""
    is_gpt5 = "gpt-5" in model.lower()
    target_model = model

    if is_gpt5 and not model.startswith("openai/"):
        if use_responses_api:
            target_model = f"openai/responses/{model}"
        else:
            target_model = f"openai/{model}"

    return target_model, is_gpt5


def prepare_completion_request(
    *,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    use_responses_api: bool = False,
    extra_params: Mapping[str, Any] | None = None,
    default_reasoning_effort: str | None = "medium",
) -> CompletionRequest:
    """Normalize model routing and provider parameters for a chat completion."""
    params: dict[str, Any] = dict(extra_params or {})
    target_model, is_gpt5 = resolve_model_name(
        model,
        use_responses_api=use_responses_api,
    )
    unsupported = get_unsupported_parameters(target_model)
    logged_max_tokens = max_tokens
    target_max_tokens = max_tokens

    if (
        is_gpt5
        and use_responses_api
        and default_reasoning_effort
        and "reasoning_effort" not in params
    ):
        params["reasoning_effort"] = default_reasoning_effort

    if is_gpt5 and target_max_tokens is not None:
        if use_responses_api:
            params["max_output_tokens"] = target_max_tokens
        else:
            params["max_completion_tokens"] = target_max_tokens
        target_max_tokens = None

    if temperature is not None and "temperature" not in unsupported:
        params["temperature"] = temperature
    if target_max_tokens is not None:
        params["max_tokens"] = target_max_tokens

    return CompletionRequest(
        model=target_model,
        params=filter_parameters(target_model, **params),
        logged_max_tokens=logged_max_tokens,
    )


def extract_response_text(response: Any) -> str:
    """Read text content from a LiteLLM response object."""
    content = response.choices[0].message.content
    if content is None:
        return ""
    return str(content)
