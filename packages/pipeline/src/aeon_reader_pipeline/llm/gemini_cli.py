"""Gemini CLI gateway — wraps the `gemini` CLI binary for LLM calls."""

from __future__ import annotations

import json
import re
import subprocess
import time

import structlog

from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
from aeon_reader_pipeline.models.config_models import ModelProfile

logger = structlog.get_logger()


class GeminiCliGateway(LlmGateway):
    """LLM gateway that delegates to the Gemini CLI.

    Uses the model from ModelProfile, with automatic fallback to
    fallback_model on failure.
    """

    def __init__(self, cli_path: str = "gemini") -> None:
        self._cli = cli_path

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        """Send a translation request via the Gemini CLI."""
        model = model_profile.model
        timeout = model_profile.cli_timeout
        result = self._call_cli(system_prompt, user_prompt, model, timeout=timeout)

        # Fallback on failure
        if result is None and model_profile.fallback_model:
            fallback = model_profile.fallback_model
            logger.warning("gemini_cli_fallback", primary=model, fallback=fallback)
            result = self._call_cli(system_prompt, user_prompt, fallback, timeout=timeout)

        if result is None:
            raise RuntimeError("Gemini CLI failed on both primary and fallback model")

        return result

    def _call_cli(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        *,
        timeout: int = 180,
    ) -> LlmResponse | None:
        """Execute a single CLI call. Returns None on failure."""
        combined_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANT: Return ONLY valid JSON. No markdown, no code fences.\n\n"
            f"{user_prompt}"
        )

        start = time.monotonic()
        try:
            proc = subprocess.run(
                [self._cli, "-m", model, "-p", combined_prompt, "-o", "text"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning("gemini_cli_timeout", model=model)
            return None

        latency_ms = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            logger.warning(
                "gemini_cli_error",
                model=model,
                exit_code=proc.returncode,
                stderr=proc.stderr[:300],
            )
            return None

        text = self._clean_output(proc.stdout)

        # Validate JSON
        try:
            json.loads(text)
        except json.JSONDecodeError:
            logger.warning("gemini_cli_non_json", model=model, raw=text[:200])
            return None

        return LlmResponse(
            text=text,
            latency_ms=latency_ms,
            provider="gemini-cli",
            model=model,
        )

    @staticmethod
    def _clean_output(raw: str) -> str:
        """Strip CLI preamble, markdown fences, and whitespace."""
        lines = raw.split("\n")
        cleaned = [
            line
            for line in lines
            if not line.startswith("Loaded cached credentials") and not line.startswith("Using ")
        ]
        text = "\n".join(cleaned).strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return text.strip()

    def provider_name(self) -> str:
        return "gemini-cli"
