"""Tests for GeminiCliGateway and CLI run paths (S5U-234).

Tests subprocess execution, fallback handling, timeout/error behavior,
clean_output, and CLI integration paths (--mock, --dry-run, --source-only).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf
import pytest
from typer.testing import CliRunner

from aeon_reader_pipeline.cli.main import app
from aeon_reader_pipeline.llm.gemini_cli import GeminiCliGateway
from aeon_reader_pipeline.models.config_models import (
    ModelProfile,
)

cli_runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# _clean_output tests
# ---------------------------------------------------------------------------


class TestCleanOutput:
    def test_plain_json(self) -> None:
        raw = '{"key": "value"}'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_markdown_json_fence(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_plain_markdown_fence(self) -> None:
        raw = '```\n{"key": "value"}\n```'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_cached_credentials_preamble(self) -> None:
        raw = 'Loaded cached credentials for user@example.com\n{"key": "value"}'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_using_preamble(self) -> None:
        raw = 'Using gemini-2.0-flash\n{"key": "value"}'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_multiple_preamble_lines(self) -> None:
        raw = 'Loaded cached credentials for test\nUsing gemini-2.0-flash\n{"key": "value"}'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_strips_whitespace(self) -> None:
        raw = '  \n  {"key": "value"}  \n  '
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_combined_preamble_and_fences(self) -> None:
        raw = 'Loaded cached credentials for test\n```json\n{"key": "value"}\n```'
        assert GeminiCliGateway._clean_output(raw) == '{"key": "value"}'

    def test_empty_string(self) -> None:
        assert GeminiCliGateway._clean_output("") == ""

    def test_preserves_internal_newlines(self) -> None:
        raw = '{"a": 1,\n"b": 2}'
        assert GeminiCliGateway._clean_output(raw) == '{"a": 1,\n"b": 2}'


# ---------------------------------------------------------------------------
# _call_cli tests (subprocess mocked)
# ---------------------------------------------------------------------------


class TestCallCli:
    def _make_gateway(self) -> GeminiCliGateway:
        return GeminiCliGateway(cli_path="/usr/bin/fake-gemini")

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_success_returns_response(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"unit_id": "u1", "translations": []}',
            stderr="",
        )
        gw = self._make_gateway()
        result = gw._call_cli("system", "user", "gemini-2.0-flash")
        assert result is not None
        assert result.provider == "gemini-cli"
        assert result.model == "gemini-2.0-flash"
        assert json.loads(result.text) == {"unit_id": "u1", "translations": []}
        assert result.latency_ms >= 0

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_timeout_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gemini", timeout=180)
        gw = self._make_gateway()
        result = gw._call_cli("system", "user", "gemini-2.0-flash", timeout=180)
        assert result is None

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_nonzero_exit_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Error: model not found",
        )
        gw = self._make_gateway()
        result = gw._call_cli("system", "user", "gemini-2.0-flash")
        assert result is None

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_invalid_json_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="This is not JSON",
            stderr="",
        )
        gw = self._make_gateway()
        result = gw._call_cli("system", "user", "gemini-2.0-flash")
        assert result is None

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_json_with_markdown_fences(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='```json\n{"result": true}\n```',
            stderr="",
        )
        gw = self._make_gateway()
        result = gw._call_cli("system", "user", "gemini-2.0-flash")
        assert result is not None
        assert json.loads(result.text) == {"result": True}

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_passes_correct_args(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true}', stderr=""
        )
        gw = GeminiCliGateway(cli_path="/path/to/gemini")
        gw._call_cli("sys prompt", "user prompt", "my-model", timeout=60)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "/path/to/gemini"
        assert cmd[1:3] == ["-m", "my-model"]
        assert "-o" in cmd and cmd[cmd.index("-o") + 1] == "text"
        assert call_args[1]["timeout"] == 60


# ---------------------------------------------------------------------------
# translate() fallback tests
# ---------------------------------------------------------------------------


class TestTranslateFallback:
    def _make_profile(self, *, model: str = "primary", fallback: str | None = None) -> ModelProfile:
        return ModelProfile(
            profile_id="test",
            provider="gemini",
            model=model,
            fallback_model=fallback,
            prompt_bundle="translate-v1",
            cli_timeout=30,
        )

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_primary_success_no_fallback(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true}', stderr=""
        )
        gw = GeminiCliGateway()
        profile = self._make_profile(model="primary-model", fallback="fallback-model")
        result = gw.translate("sys", "user", profile)
        assert result.model == "primary-model"
        # Should only be called once (no fallback needed)
        assert mock_run.call_count == 1

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_primary_fails_fallback_succeeds(self, mock_run: MagicMock) -> None:
        # First call fails (timeout), second succeeds
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="err"),
            subprocess.CompletedProcess(args=[], returncode=0, stdout='{"ok": true}', stderr=""),
        ]
        gw = GeminiCliGateway()
        profile = self._make_profile(model="primary", fallback="fallback")
        result = gw.translate("sys", "user", profile)
        assert result.model == "fallback"
        assert mock_run.call_count == 2

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_both_fail_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        gw = GeminiCliGateway()
        profile = self._make_profile(model="primary", fallback="fallback")
        with pytest.raises(RuntimeError, match="Gemini CLI failed"):
            gw.translate("sys", "user", profile)
        assert mock_run.call_count == 2

    @patch("aeon_reader_pipeline.llm.gemini_cli.subprocess.run")
    def test_no_fallback_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        gw = GeminiCliGateway()
        profile = self._make_profile(model="primary", fallback=None)
        with pytest.raises(RuntimeError, match="Gemini CLI failed"):
            gw.translate("sys", "user", profile)
        assert mock_run.call_count == 1  # No fallback attempted

    def test_provider_name(self) -> None:
        gw = GeminiCliGateway()
        assert gw.provider_name() == "gemini-cli"


# ---------------------------------------------------------------------------
# CLI integration tests (--mock, --dry-run, --source-only, inspect)
# ---------------------------------------------------------------------------


def _create_fixture_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _setup_configs(tmp_path: Path, pdf_path: Path) -> Path:
    """Create minimal config structure for CLI tests."""
    configs = tmp_path / "configs"
    docs = configs / "documents"
    docs.mkdir(parents=True)
    rules = configs / "rule-profiles"
    rules.mkdir(parents=True)
    models = configs / "model-profiles"
    models.mkdir(parents=True)
    symbols = configs / "symbol-packs"
    symbols.mkdir(parents=True)
    glossary = configs / "glossary-packs"
    glossary.mkdir(parents=True)

    # Document config
    doc_config = {
        "doc_id": "test-doc",
        "slug": "test-doc",
        "source_pdf": str(pdf_path),
        "titles": {"en": "Test", "ru": "Тест"},
        "source_locale": "en",
        "target_locale": "ru",
        "profiles": {
            "rules": "default",
            "models": "default",
            "symbols": "default",
            "glossary": "default",
        },
        "build": {"route_base": "/docs/test-doc"},
    }
    (docs / "test-doc.yaml").write_text(__import__("yaml").dump(doc_config, allow_unicode=True))

    # Rule profile
    rule = {"profile_id": "default"}
    (rules / "default.yaml").write_text(__import__("yaml").dump(rule))

    # Model profile
    model = {
        "profile_id": "default",
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "prompt_bundle": "translate-v1",
    }
    (models / "default.yaml").write_text(__import__("yaml").dump(model))

    # Symbol pack
    symbol = {"pack_id": "default", "version": "1.0.0"}
    (symbols / "default.yaml").write_text(__import__("yaml").dump(symbol))

    # Glossary pack
    gloss = {"pack_id": "default", "version": "1.0.0"}
    (glossary / "default.yaml").write_text(__import__("yaml").dump(gloss))

    # Prompt template
    prompts = tmp_path / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    return configs


class TestCLIMockRun:
    def test_mock_run_succeeds(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        configs = _setup_configs(tmp_path, pdf)
        artifacts = tmp_path / "artifacts"

        result = cli_runner.invoke(
            app,
            [
                "run",
                "--doc",
                "test-doc",
                "--configs",
                str(configs),
                "--artifact-root",
                str(artifacts),
                "--mock",
            ],
        )
        output = _strip_ansi(result.output)
        assert result.exit_code == 0, f"Failed: {output}"
        assert "Completed: test-doc" in output
        assert "mock translation gateway" in output.lower()

    def test_dry_run_shows_cost_estimate(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        configs = _setup_configs(tmp_path, pdf)
        artifacts = tmp_path / "artifacts"

        result = cli_runner.invoke(
            app,
            [
                "run",
                "--doc",
                "test-doc",
                "--configs",
                str(configs),
                "--artifact-root",
                str(artifacts),
                "--dry-run",
            ],
        )
        output = _strip_ansi(result.output)
        assert result.exit_code == 0, f"Failed: {output}"
        assert "dry run complete" in output.lower()

    def test_source_only_run_succeeds(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        configs = _setup_configs(tmp_path, pdf)
        artifacts = tmp_path / "artifacts"

        result = cli_runner.invoke(
            app,
            [
                "run",
                "--doc",
                "test-doc",
                "--configs",
                str(configs),
                "--artifact-root",
                str(artifacts),
                "--source-only",
            ],
        )
        output = _strip_ansi(result.output)
        assert result.exit_code == 0, f"Failed: {output}"
        assert "source-only" in output.lower()


class TestCLIInspect:
    def test_inspect_existing_run(self, tmp_path: Path) -> None:
        """Create a run via --mock, then inspect it."""
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        configs = _setup_configs(tmp_path, pdf)
        artifacts = tmp_path / "artifacts"

        # First, run the pipeline to create artifacts
        run_result = cli_runner.invoke(
            app,
            [
                "run",
                "--doc",
                "test-doc",
                "--configs",
                str(configs),
                "--artifact-root",
                str(artifacts),
                "--mock",
            ],
        )
        assert run_result.exit_code == 0

        # Extract run ID from output
        output = _strip_ansi(run_result.output)
        run_id_match = re.search(r"Run (\S+):", output)
        assert run_id_match, f"Could not find run ID in: {output}"
        run_id = run_id_match.group(1)

        # Inspect the run
        inspect_result = cli_runner.invoke(
            app,
            [
                "inspect",
                run_id,
                "--doc",
                "test-doc",
                "--artifact-root",
                str(artifacts),
            ],
        )
        output = _strip_ansi(inspect_result.output)
        assert inspect_result.exit_code == 0, f"Failed: {output}"
        assert run_id in output
        assert "completed" in output.lower()
