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
    """LLM gateway that delegates to the Gemini CLI (authenticated via OAuth)."""

    def __init__(self, cli_path: str = "gemini") -> None:
        self._cli = cli_path

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        """Send a translation request via the Gemini CLI."""
        combined_prompt = (
            f"{system_prompt}\n\n"
            "IMPORTANT: Return ONLY valid JSON. No markdown, no code fences, no explanation.\n\n"
            f"{user_prompt}"
        )

        start = time.monotonic()
        result = subprocess.run(
            [self._cli, "-p", combined_prompt, "-o", "text"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        if result.returncode != 0:
            raise RuntimeError(f"Gemini CLI failed (exit {result.returncode}): {result.stderr[:500]}")

        raw_output = result.stdout.strip()

        # Strip "Loaded cached credentials." prefix and any other preamble
        lines = raw_output.split("\n")
        cleaned_lines = [
            line
            for line in lines
            if not line.startswith("Loaded cached credentials")
            and not line.startswith("Using ")
        ]
        text = "\n".join(cleaned_lines).strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

        # Validate it's parseable JSON
        try:
            json.loads(text)
        except json.JSONDecodeError:
            logger.warning("gemini_cli_non_json_response", raw=text[:200])

        return LlmResponse(
            text=text,
            latency_ms=latency_ms,
            provider="gemini-cli",
            model="gemini-cli",
        )

    def provider_name(self) -> str:
        return "gemini-cli"
