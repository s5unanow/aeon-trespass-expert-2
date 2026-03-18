"""Google Gemini LLM provider adapter."""

from __future__ import annotations

import os
import random
import time
from typing import Any

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
from aeon_reader_pipeline.models.config_models import ModelProfile

logger = structlog.get_logger()

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


def _is_retryable(exc: Exception) -> bool:
    """Check whether an exception is transient and worth retrying."""
    if isinstance(exc, genai_errors.APIError) and exc.code in _RETRYABLE_STATUS_CODES:
        return True
    # httpx network / timeout errors surface through the SDK
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def _backoff_delay(attempt: int, base: float, maximum: float) -> float:
    """Exponential backoff with full jitter: uniform(0, min(max, base * 2^attempt))."""
    delay = min(maximum, base * (2 ** (attempt - 1)))
    return random.uniform(0, delay)


class GeminiProvider(LlmGateway):
    """Gemini provider adapter using google-genai SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("GOOGLE_API_KEY")
        if key:
            self._client = genai.Client(api_key=key)
        else:
            self._client = genai.Client()

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        """Send translation request to Gemini with retry + exponential backoff."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=model_profile.temperature,
            top_p=model_profile.top_p,
            max_output_tokens=model_profile.max_output_tokens,
            response_mime_type="application/json",
        )

        max_retries = model_profile.max_retries
        base_delay = model_profile.retry_base_delay
        max_delay = model_profile.retry_max_delay
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                start = time.monotonic()
                response = self._client.models.generate_content(
                    model=model_profile.model,
                    contents=user_prompt,
                    config=config,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                text = response.text or ""
                metadata: dict[str, Any] = {}

                input_tokens = 0
                output_tokens = 0
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count or 0
                    output_tokens = response.usage_metadata.candidates_token_count or 0

                return LlmResponse(
                    text=text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    provider="gemini",
                    model=model_profile.model,
                    raw_metadata=metadata,
                )

            except Exception as exc:
                last_exc = exc
                if not _is_retryable(exc) or attempt == max_retries:
                    if attempt > 1:
                        logger.error(
                            "gemini_request_failed_after_retries",
                            attempt=attempt,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )
                    raise

                delay = _backoff_delay(attempt, base_delay, max_delay)
                logger.warning(
                    "gemini_request_retrying",
                    attempt=attempt,
                    max_retries=max_retries,
                    delay_s=round(delay, 2),
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                time.sleep(delay)

        # Unreachable, but keeps mypy happy
        assert last_exc is not None
        raise last_exc  # pragma: no cover

    def provider_name(self) -> str:
        return "gemini"
