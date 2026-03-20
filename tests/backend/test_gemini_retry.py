"""Tests for ModelProfile retry/timeout validation fields."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from aeon_reader_pipeline.models.config_models import ModelProfile


def _make_profile(**overrides: object) -> ModelProfile:
    defaults = {
        "profile_id": "test",
        "provider": "gemini-cli",
        "model": "gemini-2.5-flash",
        "max_retries": 3,
        "retry_base_delay": 0.01,
        "retry_max_delay": 0.1,
    }
    defaults.update(overrides)
    return ModelProfile(**defaults)  # type: ignore[arg-type]


class TestModelProfileRetryValidation:
    def test_max_retries_must_be_at_least_1(self) -> None:
        with pytest.raises(PydanticValidationError):
            _make_profile(max_retries=0)

    def test_negative_max_retries_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            _make_profile(max_retries=-1)

    def test_negative_base_delay_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            _make_profile(retry_base_delay=-0.5)

    def test_negative_max_delay_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            _make_profile(retry_max_delay=-1.0)

    def test_cli_timeout_default(self) -> None:
        profile = _make_profile()
        assert profile.cli_timeout == 180

    def test_cli_timeout_custom(self) -> None:
        profile = _make_profile(cli_timeout=300)
        assert profile.cli_timeout == 300

    def test_cli_timeout_must_be_positive(self) -> None:
        with pytest.raises(PydanticValidationError):
            _make_profile(cli_timeout=0)

        with pytest.raises(PydanticValidationError):
            _make_profile(cli_timeout=-10)
