"""Tests for GeminiProvider retry + exponential backoff logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError as PydanticValidationError

from aeon_reader_pipeline.llm.gemini import (
    GeminiProvider,
    _backoff_delay,
    _is_retryable,
)
from aeon_reader_pipeline.models.config_models import ModelProfile


def _make_profile(**overrides: object) -> ModelProfile:
    defaults = {
        "profile_id": "test",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "max_retries": 3,
        "retry_base_delay": 0.01,
        "retry_max_delay": 0.1,
    }
    defaults.update(overrides)
    return ModelProfile(**defaults)  # type: ignore[arg-type]


# ─── _is_retryable ───────────────────────────────────────────────────────


class TestIsRetryable:
    def test_rate_limit_429(self) -> None:
        exc = genai_errors.APIError(429, {"error": "rate limited"})
        assert _is_retryable(exc) is True

    def test_server_error_500(self) -> None:
        exc = genai_errors.ServerError(500, {"error": "internal"})
        assert _is_retryable(exc) is True

    def test_server_error_503(self) -> None:
        exc = genai_errors.ServerError(503, {"error": "overloaded"})
        assert _is_retryable(exc) is True

    def test_client_error_400_not_retryable(self) -> None:
        exc = genai_errors.ClientError(400, {"error": "bad request"})
        assert _is_retryable(exc) is False

    def test_client_error_401_not_retryable(self) -> None:
        exc = genai_errors.ClientError(401, {"error": "unauthorized"})
        assert _is_retryable(exc) is False

    def test_timeout_error_retryable(self) -> None:
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_connection_error_retryable(self) -> None:
        assert _is_retryable(ConnectionError("refused")) is True

    def test_os_error_retryable(self) -> None:
        assert _is_retryable(OSError("network unreachable")) is True

    def test_server_error_502_retryable(self) -> None:
        exc = genai_errors.ServerError(502, {"error": "bad gateway"})
        assert _is_retryable(exc) is True

    def test_value_error_not_retryable(self) -> None:
        assert _is_retryable(ValueError("bad value")) is False


# ─── _backoff_delay ──────────────────────────────────────────────────────


class TestBackoffDelay:
    def test_respects_maximum(self) -> None:
        for _ in range(50):
            delay = _backoff_delay(attempt=10, base=1.0, maximum=5.0)
            assert 0 <= delay <= 5.0

    def test_first_attempt_bounded_by_base(self) -> None:
        for _ in range(50):
            delay = _backoff_delay(attempt=1, base=2.0, maximum=60.0)
            assert 0 <= delay <= 2.0

    def test_grows_with_attempts(self) -> None:
        # Average delay should increase with attempt number (statistical check)
        low_delays = [_backoff_delay(1, 1.0, 60.0) for _ in range(200)]
        high_delays = [_backoff_delay(5, 1.0, 60.0) for _ in range(200)]
        assert sum(low_delays) / len(low_delays) < sum(high_delays) / len(high_delays)


# ─── GeminiProvider.translate retry integration ──────────────────────────


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent actual sleeping during retry tests."""
    monkeypatch.setattr("aeon_reader_pipeline.llm.gemini.time.sleep", lambda _: None)


class TestGeminiRetry:
    """Test retry logic via GeminiProvider.translate with mocked SDK client."""

    def _make_provider(self) -> GeminiProvider:
        """Create a provider with a mocked client."""
        with patch("aeon_reader_pipeline.llm.gemini.genai.Client"):
            provider = GeminiProvider(api_key="test-key")
        return provider

    def _make_success_response(self) -> MagicMock:
        resp = MagicMock()
        resp.text = '{"translations": []}'
        resp.usage_metadata.prompt_token_count = 10
        resp.usage_metadata.candidates_token_count = 5
        return resp

    def test_success_on_first_attempt(self) -> None:
        provider = self._make_provider()
        provider._client.models.generate_content = MagicMock(
            return_value=self._make_success_response()
        )
        profile = _make_profile()

        result = provider.translate("system", "user", profile)

        assert result.text == '{"translations": []}'
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert provider._client.models.generate_content.call_count == 1

    def test_retry_on_429_then_succeed(self) -> None:
        provider = self._make_provider()
        rate_limit = genai_errors.APIError(429, {"error": "rate limited"})
        provider._client.models.generate_content = MagicMock(
            side_effect=[rate_limit, self._make_success_response()]
        )
        profile = _make_profile()

        result = provider.translate("system", "user", profile)

        assert result.text == '{"translations": []}'
        assert provider._client.models.generate_content.call_count == 2

    def test_retry_on_500_then_succeed(self) -> None:
        provider = self._make_provider()
        server_err = genai_errors.ServerError(500, {"error": "internal"})
        provider._client.models.generate_content = MagicMock(
            side_effect=[server_err, self._make_success_response()]
        )
        profile = _make_profile()

        result = provider.translate("system", "user", profile)

        assert result.text == '{"translations": []}'
        assert provider._client.models.generate_content.call_count == 2

    def test_retry_on_timeout_then_succeed(self) -> None:
        provider = self._make_provider()
        provider._client.models.generate_content = MagicMock(
            side_effect=[TimeoutError("timed out"), self._make_success_response()]
        )
        profile = _make_profile()

        result = provider.translate("system", "user", profile)

        assert result.text == '{"translations": []}'
        assert provider._client.models.generate_content.call_count == 2

    def test_exhaust_retries_raises(self) -> None:
        provider = self._make_provider()
        server_err = genai_errors.ServerError(503, {"error": "overloaded"})
        provider._client.models.generate_content = MagicMock(
            side_effect=[server_err, server_err, server_err]
        )
        profile = _make_profile(max_retries=3)

        with pytest.raises(genai_errors.ServerError):
            provider.translate("system", "user", profile)

        assert provider._client.models.generate_content.call_count == 3

    def test_non_retryable_error_raises_immediately(self) -> None:
        provider = self._make_provider()
        client_err = genai_errors.ClientError(400, {"error": "bad request"})
        provider._client.models.generate_content = MagicMock(side_effect=client_err)
        profile = _make_profile()

        with pytest.raises(genai_errors.ClientError):
            provider.translate("system", "user", profile)

        assert provider._client.models.generate_content.call_count == 1

    def test_retry_logging(self) -> None:
        provider = self._make_provider()
        rate_limit = genai_errors.APIError(429, {"error": "rate limited"})
        provider._client.models.generate_content = MagicMock(
            side_effect=[rate_limit, self._make_success_response()]
        )
        profile = _make_profile()

        with patch("aeon_reader_pipeline.llm.gemini.logger") as mock_logger:
            provider.translate("system", "user", profile)

            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[0][0] == "gemini_request_retrying"
            assert call_kwargs[1]["attempt"] == 1

    def test_single_retry_config(self) -> None:
        """With max_retries=1, no retry happens."""
        provider = self._make_provider()
        server_err = genai_errors.ServerError(500, {"error": "internal"})
        provider._client.models.generate_content = MagicMock(side_effect=server_err)
        profile = _make_profile(max_retries=1)

        with pytest.raises(genai_errors.ServerError):
            provider.translate("system", "user", profile)

        assert provider._client.models.generate_content.call_count == 1

    def test_connection_error_retries(self) -> None:
        provider = self._make_provider()
        provider._client.models.generate_content = MagicMock(
            side_effect=[
                ConnectionError("refused"),
                ConnectionError("refused"),
                self._make_success_response(),
            ]
        )
        profile = _make_profile()

        result = provider.translate("system", "user", profile)

        assert result.text == '{"translations": []}'
        assert provider._client.models.generate_content.call_count == 3


# ─── ModelProfile validation ─────────────────────────────────────────────


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
