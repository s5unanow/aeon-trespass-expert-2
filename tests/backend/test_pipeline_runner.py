"""Tests for PipelineRunner execution, skip logic, and manifest tracking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.models.config_models import (
    DocumentBuild,
    DocumentConfig,
    DocumentProfiles,
    DocumentTitles,
    GlossaryPack,
    ModelProfile,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.runner import PipelineRunner


class _DummyStage(BaseStage):
    """Minimal stage for testing runner behaviour."""

    name = "resolve_run"
    version = "1.0.0"
    description = "dummy"

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.executed = False

    def execute(self, ctx: StageContext) -> None:
        self.executed = True
        if self._fail:
            raise RuntimeError("stage failed on purpose")

    def should_skip(self, ctx: StageContext) -> bool:
        return False


class _SkippableStage(_DummyStage):
    """Stage that reports it can be skipped."""

    def should_skip(self, ctx: StageContext) -> bool:
        return True


def _make_ctx(tmp_path: Path, *, cache_mode: str = "read_write") -> StageContext:
    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("test-run", ["test-doc"])
    return StageContext(
        run_id="test-run",
        doc_id="test-doc",
        pipeline_config=PipelineConfig(
            run_id="test-run",
            cache_mode=cache_mode,  # type: ignore[arg-type]
        ),
        document_config=DocumentConfig(
            doc_id="test-doc",
            slug="test-doc",
            source_pdf="fake.pdf",
            titles=DocumentTitles(en="Test", ru="Тест"),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(
            profile_id="test",
            provider="gemini",
            model="gemini-2.0-flash",
            prompt_bundle="translate-v1",
        ),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=tmp_path / "configs",
    )


def _patch_registry(stage: BaseStage):
    """Return patches that make the runner see only the given stage."""
    return [
        patch(
            "aeon_reader_pipeline.stage_framework.runner.filter_stages",
            return_value=[stage.name],
        ),
        patch(
            "aeon_reader_pipeline.stage_framework.runner.get_registered_stages",
            return_value=[stage.name],
        ),
        patch(
            "aeon_reader_pipeline.stage_framework.runner.get_stage",
            return_value=stage,
        ),
    ]


class TestPipelineRunnerExecution:
    """Verify runner executes stages and updates manifests."""

    def test_run_executes_stage(self, tmp_path: Path) -> None:
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)
            assert stage.executed
        finally:
            for p in patches:
                p.stop()

    def test_run_manifest_completed_after_success(self, tmp_path: Path) -> None:
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)
            manifest = ctx.artifact_store.load_run_manifest("test-run")
            assert manifest.status == "completed"
            assert manifest.completed_at is not None
        finally:
            for p in patches:
                p.stop()

    def test_failed_stage_raises_and_updates_manifest(self, tmp_path: Path) -> None:
        stage = _DummyStage(fail=True)
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            with pytest.raises(RuntimeError, match="stage failed on purpose"):
                PipelineRunner().run(ctx)

            stage_manifest = ctx.artifact_store.load_stage_manifest(
                "test-run", "test-doc", "resolve_run"
            )
            assert stage_manifest is not None
            assert stage_manifest.status == "failed"
            assert stage_manifest.error == "stage failed on purpose"
        finally:
            for p in patches:
                p.stop()

    def test_stage_manifest_has_timing_and_cache_key(self, tmp_path: Path) -> None:
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)

            stage_manifest = ctx.artifact_store.load_stage_manifest(
                "test-run", "test-doc", "resolve_run"
            )
            assert stage_manifest is not None
            assert stage_manifest.status == "completed"
            assert stage_manifest.started_at is not None
            assert stage_manifest.completed_at is not None
            assert "duration_ms" in stage_manifest.metrics
            assert "cache_key" in stage_manifest.metrics
        finally:
            for p in patches:
                p.stop()


class TestPipelineRunnerSkipLogic:
    """Verify cache_mode skip behaviour."""

    def test_skippable_stage_skipped_in_read_write(self, tmp_path: Path) -> None:
        stage = _SkippableStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="read_write")
            PipelineRunner().run(ctx)
            assert not stage.executed
        finally:
            for p in patches:
                p.stop()

    def test_skippable_stage_forced_in_force_refresh(self, tmp_path: Path) -> None:
        stage = _SkippableStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="force_refresh")
            PipelineRunner().run(ctx)
            assert stage.executed
        finally:
            for p in patches:
                p.stop()

    def test_skippable_stage_forced_in_off_mode(self, tmp_path: Path) -> None:
        stage = _SkippableStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="off")
            PipelineRunner().run(ctx)
            assert stage.executed
        finally:
            for p in patches:
                p.stop()

    def test_skippable_stage_forced_in_write_only(self, tmp_path: Path) -> None:
        stage = _SkippableStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="write_only")
            PipelineRunner().run(ctx)
            assert stage.executed
        finally:
            for p in patches:
                p.stop()
