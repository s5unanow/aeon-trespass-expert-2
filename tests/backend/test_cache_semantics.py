"""Tests for cache semantics, resume, and stage manifest population."""

from __future__ import annotations

from pathlib import Path

import pymupdf

import aeon_reader_pipeline.stages  # noqa: F401 — triggers stage registration
from aeon_reader_pipeline.cache.keys import build_cache_key, stage_cache_key
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
from aeon_reader_pipeline.models.run_models import PipelineConfig, StageManifest
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.runner import PipelineRunner


def _create_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_ctx(
    tmp_path: Path,
    *,
    cache_mode: str = "read_write",
    from_stage: str = "resolve_run",
    to_stage: str = "ingest_source",
) -> StageContext:
    pdf = tmp_path / "source.pdf"
    _create_pdf(pdf)
    configs_root = tmp_path / "configs"
    configs_root.mkdir(exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    run_id = "run-test"
    doc_id = "test-doc"
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(
            run_id=run_id,
            stages={"from_stage": from_stage, "to_stage": to_stage},
            cache_mode=cache_mode,
        ),
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test",
            source_pdf=str(pdf),
            titles=DocumentTitles(en="Test", ru="Тест"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="default",
                models="default",
                symbols="default",
                glossary="default",
            ),
            build=DocumentBuild(route_base="/docs/test"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(profile_id="test", provider="gemini", model="gemini-2.0-flash"),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


class TestCacheKeys:
    def test_deterministic(self) -> None:
        k1 = build_cache_key(a="x", b="y")
        k2 = build_cache_key(a="x", b="y")
        assert k1 == k2

    def test_order_independent(self) -> None:
        k1 = build_cache_key(a="x", b="y")
        k2 = build_cache_key(b="y", a="x")
        assert k1 == k2

    def test_different_inputs_different_keys(self) -> None:
        k1 = build_cache_key(a="x")
        k2 = build_cache_key(a="y")
        assert k1 != k2

    def test_stage_cache_key(self) -> None:
        k = stage_cache_key(
            stage_name="ingest_source",
            stage_version="1.0.0",
            doc_hash="abc",
        )
        assert len(k) == 64  # SHA-256 hex

    def test_stage_version_changes_key(self) -> None:
        k1 = stage_cache_key(stage_name="s", stage_version="1.0.0")
        k2 = stage_cache_key(stage_name="s", stage_version="2.0.0")
        assert k1 != k2


class TestCacheModeSkipBehavior:
    """Test that cache_mode controls whether completed stages are skipped."""

    def test_read_write_skips_completed(self, tmp_path: Path) -> None:
        """Default mode: completed stages are skipped on re-run."""
        ctx = _make_ctx(tmp_path, cache_mode="read_write")
        runner = PipelineRunner()
        runner.run(ctx)

        # Run again — stages should be skipped
        runner.run(ctx)

        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        for s in manifest.stages:
            assert s.status in ("completed", "skipped")

    def test_force_refresh_reruns_completed(self, tmp_path: Path) -> None:
        """force_refresh mode: completed stages are re-run."""
        ctx = _make_ctx(tmp_path, cache_mode="read_write")
        runner = PipelineRunner()
        runner.run(ctx)

        # Change to force_refresh and re-run
        ctx.pipeline_config = ctx.pipeline_config.model_copy(update={"cache_mode": "force_refresh"})
        runner.run(ctx)

        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        # All stages should be completed (not skipped)
        for s in manifest.stages:
            assert s.status == "completed"

    def test_off_mode_never_skips(self, tmp_path: Path) -> None:
        """off mode: never skips, always re-runs."""
        ctx = _make_ctx(tmp_path, cache_mode="off")
        runner = PipelineRunner()
        runner.run(ctx)

        # Run again with off — should re-run
        runner.run(ctx)

        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        for s in manifest.stages:
            assert s.status == "completed"


class TestStageManifestPopulation:
    """Test that stage manifests are populated with hashes and metrics."""

    def test_input_hashes_populated(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        PipelineRunner().run(ctx)

        # Check the resolve_run stage manifest
        sm = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, "resolve_run")
        assert sm is not None
        assert "document_config" in sm.input_hashes
        assert "rule_profile" in sm.input_hashes
        assert "model_profile" in sm.input_hashes
        assert len(sm.input_hashes["document_config"]) == 64

    def test_metrics_populated(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        PipelineRunner().run(ctx)

        sm = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, "resolve_run")
        assert sm is not None
        assert "duration_ms" in sm.metrics
        assert isinstance(sm.metrics["duration_ms"], int)
        assert "cache_key" in sm.metrics
        assert len(sm.metrics["cache_key"]) == 64

    def test_timing_recorded(self, tmp_path: Path) -> None:
        ctx = _make_ctx(tmp_path)
        PipelineRunner().run(ctx)

        sm = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, "resolve_run")
        assert sm is not None
        assert sm.started_at is not None
        assert sm.completed_at is not None
        assert sm.completed_at >= sm.started_at


class TestResumeSemantics:
    """Test that a re-run resumes from where the previous run left off."""

    def test_resume_skips_completed_stages(self, tmp_path: Path) -> None:
        """Stages that completed in a prior run are skipped on resume."""
        ctx = _make_ctx(tmp_path)
        runner = PipelineRunner()
        runner.run(ctx)

        # Verify first run completed both stages
        sm = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, "resolve_run")
        assert sm is not None
        assert sm.status == "completed"

        # Re-run — resolve_run should be skipped
        runner.run(ctx)

        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        resolve_status = next(s for s in manifest.stages if s.stage_name == "resolve_run")
        assert resolve_status.status == "skipped"

    def test_failed_stage_is_retried(self, tmp_path: Path) -> None:
        """A stage that previously failed is retried on resume."""
        ctx = _make_ctx(tmp_path)

        # Write a "failed" manifest for resolve_run
        failed_manifest = StageManifest(
            stage_name="resolve_run",
            stage_version="1.0.0",
            status="failed",
            error="simulated failure",
        )
        ctx.artifact_store.save_stage_manifest(ctx.run_id, ctx.doc_id, failed_manifest)

        # Run pipeline — should retry resolve_run (not skip it)
        runner = PipelineRunner()
        runner.run(ctx)

        sm = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, "resolve_run")
        assert sm is not None
        assert sm.status == "completed"


class TestArtifactEnvelopeRemoved:
    """Verify the dead ArtifactEnvelope abstraction was removed."""

    def test_no_artifact_envelope_class(self) -> None:
        """ArtifactEnvelope should not be importable."""
        from aeon_reader_pipeline.models import base

        assert not hasattr(base, "ArtifactEnvelope")
        assert not hasattr(base, "Provenance")
