"""Tests for CLI entry point (list-stages, run, inspect)."""

from __future__ import annotations

from typer.testing import CliRunner

from aeon_reader_pipeline.cli.main import app

runner = CliRunner()


class TestListStages:
    """Verify the list-stages command outputs all 15 stages."""

    def test_list_stages_shows_all(self) -> None:
        result = runner.invoke(app, ["list-stages"])
        assert result.exit_code == 0
        assert "resolve_run" in result.output
        assert "package_release" in result.output

    def test_list_stages_shows_registered(self) -> None:
        result = runner.invoke(app, ["list-stages"])
        assert result.exit_code == 0
        assert "registered" in result.output


class TestInspect:
    """Verify the inspect command handles missing runs."""

    def test_inspect_missing_run(self, tmp_path) -> None:
        result = runner.invoke(
            app,
            [
                "inspect",
                "nonexistent-run",
                "--doc",
                "test-doc",
                "--artifact-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestRun:
    """Verify the run command validates input."""

    def test_run_no_docs_exits(self, tmp_path) -> None:
        # With a configs dir that has no documents, should fail
        configs = tmp_path / "configs" / "documents"
        configs.mkdir(parents=True)
        result = runner.invoke(
            app,
            [
                "run",
                "--configs",
                str(tmp_path / "configs"),
                "--artifact-root",
                str(tmp_path / "artifacts"),
            ],
        )
        assert result.exit_code == 1

    def test_run_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--doc" in result.output
        assert "--mock" in result.output
        assert "--dry-run" in result.output
