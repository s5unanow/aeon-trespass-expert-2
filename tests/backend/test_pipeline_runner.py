"""Tests for PipelineRunner execution, skip logic, and manifest tracking."""

from __future__ import annotations

import contextlib
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


class _ManifestAwareStage(BaseStage):
    """Stage that uses the default manifest-based should_skip logic."""

    name = "resolve_run"
    version = "1.0.0"
    description = "manifest aware"

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.executed = False

    def execute(self, ctx: StageContext) -> None:
        self.executed = True
        if self._fail:
            raise RuntimeError("stage failed on purpose")


class _WritingStage(_DummyStage):
    """Stage that writes an artifact file during execution."""

    def execute(self, ctx: StageContext) -> None:
        self.executed = True
        stage_dir = ctx.artifact_store.ensure_stage_dir(ctx.run_id, ctx.doc_id, self.name)
        (stage_dir / "output.json").write_text('{"result": "ok"}')


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


class TestCacheKeyValidation:
    """Verify that cache key comparison drives skip decisions."""

    def test_stage_skipped_when_cache_key_matches(self, tmp_path: Path) -> None:
        """First run completes; second run with same inputs skips."""
        stage = _ManifestAwareStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)
            assert stage.executed

            # Second run — same inputs, same run_id → manifest exists with matching key
            stage2 = _ManifestAwareStage()
            for p in patches:
                p.stop()
            patches2 = _patch_registry(stage2)
            for p in patches2:
                p.start()
            PipelineRunner().run(ctx)
            assert not stage2.executed
        finally:
            for p in patches:
                with contextlib.suppress(RuntimeError):
                    p.stop()
            for p in patches2:
                with contextlib.suppress(RuntimeError):
                    p.stop()

    def test_stage_reruns_when_inputs_change(self, tmp_path: Path) -> None:
        """A completed stage reruns when input hashes change."""
        stage = _ManifestAwareStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)
            assert stage.executed

            # Change inputs (different model profile → different cache key)
            ctx.model_profile = ModelProfile(
                profile_id="changed",
                provider="gemini",
                model="gemini-2.5-pro",
                prompt_bundle="translate-v2",
            )

            stage2 = _ManifestAwareStage()
            for p in patches:
                p.stop()
            patches2 = _patch_registry(stage2)
            for p in patches2:
                p.start()
            PipelineRunner().run(ctx)
            assert stage2.executed  # Must rerun — inputs changed
        finally:
            for p in patches:
                with contextlib.suppress(RuntimeError):
                    p.stop()
            for p in patches2:
                with contextlib.suppress(RuntimeError):
                    p.stop()


class TestReadOnlyMode:
    """Verify read_only cache mode behaviour."""

    def test_read_only_skips_on_cache_miss(self, tmp_path: Path) -> None:
        """read_only mode skips a stage that has no cached output."""
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="read_only")
            PipelineRunner().run(ctx)
            assert not stage.executed
        finally:
            for p in patches:
                p.stop()

    def test_read_only_uses_cached_stage(self, tmp_path: Path) -> None:
        """read_only mode skips (cache hit) when a valid manifest exists."""
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            # First run: populate cache in read_write mode
            ctx = _make_ctx(tmp_path, cache_mode="read_write")
            PipelineRunner().run(ctx)
            assert stage.executed

            # Second run: read_only — stage should be skipped (cache hit)
            ctx2 = _make_ctx(tmp_path, cache_mode="read_only")
            # Reuse same artifact store so manifests are visible
            ctx2.artifact_store = ctx.artifact_store
            stage2 = _DummyStage()
            for p in patches:
                p.stop()
            patches2 = _patch_registry(stage2)
            for p in patches2:
                p.start()
            PipelineRunner().run(ctx2)
            assert not stage2.executed
        finally:
            for p in patches:
                with contextlib.suppress(RuntimeError):
                    p.stop()
            for p in patches2:
                with contextlib.suppress(RuntimeError):
                    p.stop()


class TestOutputHashes:
    """Verify that output hashes are populated after stage execution."""

    def test_output_hashes_populated(self, tmp_path: Path) -> None:
        stage = _WritingStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)

            sm = ctx.artifact_store.load_stage_manifest("test-run", "test-doc", "resolve_run")
            assert sm is not None
            assert "output.json" in sm.output_hashes
            assert len(sm.output_hashes["output.json"]) == 64  # SHA-256 hex
        finally:
            for p in patches:
                p.stop()


class TestCacheStats:
    """Verify that cache hit/miss counters are tracked."""

    def test_miss_counted_on_execution(self, tmp_path: Path) -> None:
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)

            rm = ctx.artifact_store.load_run_manifest("test-run")
            assert rm.cache_stats["misses"] == 1
        finally:
            for p in patches:
                p.stop()

    def test_hit_counted_on_skip(self, tmp_path: Path) -> None:
        stage = _SkippableStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path, cache_mode="read_write")
            PipelineRunner().run(ctx)

            rm = ctx.artifact_store.load_run_manifest("test-run")
            assert rm.cache_stats["hits"] == 1
        finally:
            for p in patches:
                p.stop()


class TestWorkUnitTracking:
    """Verify that work units reported by stages appear in the manifest."""

    def test_work_units_in_manifest(self, tmp_path: Path) -> None:
        class _UnitTrackingStage(_DummyStage):
            def execute(self, ctx: StageContext) -> None:
                self.executed = True
                ctx.work_units.record("page-1", "completed")
                ctx.work_units.record("page-2", "failed", error="bad parse")

        stage = _UnitTrackingStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)

            sm = ctx.artifact_store.load_stage_manifest("test-run", "test-doc", "resolve_run")
            assert sm is not None
            assert len(sm.work_units) == 2
            ids = [wu.unit_id for wu in sm.work_units]
            assert "page-1" in ids
            assert "page-2" in ids
            failed = [wu for wu in sm.work_units if wu.status == "failed"]
            assert len(failed) == 1
            assert failed[0].error == "bad parse"
        finally:
            for p in patches:
                p.stop()


class TestResumeAfterFailure:
    """Verify that a failed run can be resumed from the last successful stage."""

    def test_resume_skips_completed_reruns_failed(self, tmp_path: Path) -> None:
        """Run with a passing then failing stage.  Resume skips the first."""
        stage_a = _ManifestAwareStage()
        stage_a.name = "resolve_run"

        stage_b = _ManifestAwareStage(fail=True)
        stage_b.name = "ingest_source"

        def _get_stage_dispatch(name: str) -> BaseStage:
            return {"resolve_run": stage_a, "ingest_source": stage_b}[name]

        patches = [
            patch(
                "aeon_reader_pipeline.stage_framework.runner.filter_stages",
                return_value=["resolve_run", "ingest_source"],
            ),
            patch(
                "aeon_reader_pipeline.stage_framework.runner.get_registered_stages",
                return_value=["resolve_run", "ingest_source"],
            ),
            patch(
                "aeon_reader_pipeline.stage_framework.runner.get_stage",
                side_effect=_get_stage_dispatch,
            ),
        ]
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            with pytest.raises(RuntimeError):
                PipelineRunner().run(ctx)

            assert stage_a.executed
            assert stage_b.executed

            # Resume — stage_a should be skipped (completed), stage_b retried
            stage_a2 = _ManifestAwareStage()
            stage_a2.name = "resolve_run"
            stage_b2 = _ManifestAwareStage()  # no longer fails
            stage_b2.name = "ingest_source"

            def _dispatch2(name: str) -> BaseStage:
                return {"resolve_run": stage_a2, "ingest_source": stage_b2}[name]

            for p in patches:
                p.stop()
            patches2 = [
                patch(
                    "aeon_reader_pipeline.stage_framework.runner.filter_stages",
                    return_value=["resolve_run", "ingest_source"],
                ),
                patch(
                    "aeon_reader_pipeline.stage_framework.runner.get_registered_stages",
                    return_value=["resolve_run", "ingest_source"],
                ),
                patch(
                    "aeon_reader_pipeline.stage_framework.runner.get_stage",
                    side_effect=_dispatch2,
                ),
            ]
            for p in patches2:
                p.start()

            PipelineRunner().run(ctx)
            assert not stage_a2.executed  # skipped — already completed
            assert stage_b2.executed  # retried — was failed
        finally:
            for p in patches:
                with contextlib.suppress(RuntimeError):
                    p.stop()
            for p in patches2:
                with contextlib.suppress(RuntimeError):
                    p.stop()


class TestInputHashesPopulated:
    """Verify that stage manifests contain input hashes."""

    def test_input_hashes_present(self, tmp_path: Path) -> None:
        stage = _DummyStage()
        patches = _patch_registry(stage)
        for p in patches:
            p.start()
        try:
            ctx = _make_ctx(tmp_path)
            PipelineRunner().run(ctx)

            sm = ctx.artifact_store.load_stage_manifest("test-run", "test-doc", "resolve_run")
            assert sm is not None
            assert "document_config" in sm.input_hashes
            assert "rule_profile" in sm.input_hashes
            assert "model_profile" in sm.input_hashes
            assert "symbol_pack" in sm.input_hashes
            assert "glossary_pack" in sm.input_hashes
            for v in sm.input_hashes.values():
                assert len(v) == 64  # SHA-256 hex
        finally:
            for p in patches:
                p.stop()
