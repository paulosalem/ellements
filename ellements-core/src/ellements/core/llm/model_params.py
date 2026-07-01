"""Model-specific parameter filtering helpers for LiteLLM calls."""

from __future__ import annotations

import re
import warnings
from typing import Any

# Model-specific parameter compatibility
# Maps model patterns to sets of unsupported parameters.
MODEL_PARAMETER_RESTRICTIONS = {
    r"(openai/(responses/)?)?gpt-5(-.*)?": {
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "logprobs",
        "top_logprobs",
        "logit_bias",
        "max_tokens",
    },
    r"o[34](-.*)?": {
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "logprobs",
        "top_logprobs",
        "logit_bias",
    },
}


def get_unsupported_parameters(model: str) -> set[str]:
    """Get the set of unsupported parameters for a given model."""
    unsupported = set()

    for pattern, restricted_params in MODEL_PARAMETER_RESTRICTIONS.items():
        if re.match(pattern, model, re.IGNORECASE):
            unsupported.update(restricted_params)

    return unsupported


def filter_parameters(model: str, **kwargs: Any) -> dict[str, Any]:
    """Filter out parameters that are not supported by the given model."""
    unsupported = get_unsupported_parameters(model)

    filtered = {
        key: value
        for key, value in kwargs.items()
        if key not in unsupported and value is not None
    }

    removed = set(kwargs.keys()) - set(filtered.keys())
    removed_unsupported = {key for key in removed if kwargs[key] is not None}

    if removed_unsupported:
        warnings.warn(
            f"Model '{model}' does not support parameters: {', '.join(sorted(removed_unsupported))}. "
            f"These parameters have been automatically filtered out.",
            UserWarning,
            stacklevel=3,
        )

    return filtered
