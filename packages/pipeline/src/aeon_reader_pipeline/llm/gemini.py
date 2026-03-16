"""Google Gemini LLM provider adapter."""

from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import types

from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
from aeon_reader_pipeline.models.config_models import ModelProfile


class GeminiProvider(LlmGateway):
    """Gemini provider adapter using google-genai SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        """Send translation request to Gemini."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=model_profile.temperature,
            top_p=model_profile.top_p,
            max_output_tokens=model_profile.max_output_tokens,
            response_mime_type="application/json",
        )

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

    def provider_name(self) -> str:
        return "gemini"
