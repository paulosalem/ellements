"""Tests for model parameter filtering."""

from __future__ import annotations

import pytest
from ellements.core.llm import filter_parameters, get_unsupported_parameters


class TestParameterFiltering:
    def test_gpt5_unsupported_parameters(self):
        unsupported = get_unsupported_parameters("gpt-5-mini")
        for param in (
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
            "logprobs",
            "top_logprobs",
            "logit_bias",
            "max_tokens",
        ):
            assert param in unsupported

    def test_o3_unsupported_parameters(self):
        unsupported = get_unsupported_parameters("o3")
        assert "temperature" in unsupported
        assert "max_tokens" not in unsupported

    def test_gpt4_supports_all(self):
        assert get_unsupported_parameters("gpt-4.1-mini") == set()

    def test_filter_parameters_gpt5(self):
        params = {"temperature": 0.7, "max_tokens": 1000, "top_p": 0.9}
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            filtered = filter_parameters("gpt-5-mini", **params)
        for unsupported in ("temperature", "max_tokens", "top_p"):
            assert unsupported not in filtered

    def test_filter_parameters_gpt4_passthrough(self):
        params = {"temperature": 0.7, "max_tokens": 1000}
        assert filter_parameters("gpt-4.1-mini", **params) == params

    def test_filter_parameters_strips_none(self):
        filtered = filter_parameters(
            "gpt-4.1-mini", temperature=0.7, max_tokens=None
        )
        assert "temperature" in filtered
        assert "max_tokens" not in filtered

    def test_case_insensitive_model_match(self):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            filtered = filter_parameters("GPT-5-MINI", temperature=0.7)
        assert "temperature" not in filtered

    def test_filter_parameters_warns(self):
        with pytest.warns(UserWarning, match="does not support parameters"):
            filter_parameters("gpt-5-mini", temperature=0.7)
