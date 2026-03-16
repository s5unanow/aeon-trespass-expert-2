"""Abstract base class for LLM provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.config_models import ModelProfile


class LlmResponse(BaseModel):
    """Raw response from an LLM provider."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = ""
    model: str = ""
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class LlmGateway(ABC):
    """Abstract gateway for LLM calls.

    Stage code talks only to this interface — never to provider SDKs directly.
    """

    @abstractmethod
    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        """Send a translation request and return the raw text response."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier (e.g., 'gemini')."""
        ...
