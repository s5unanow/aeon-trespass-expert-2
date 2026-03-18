"""Tests for the resolve_run stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf

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
from aeon_reader_pipeline.models.run_models import (
    PipelineConfig,
    ResolvedRunPlan,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.resolve_run import (
    ResolveRunStage,
    _hash_prompt_bundle,
    _resolve_doc,
)


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id=run_id),
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test", ru="\u0422\u0435\u0441\u0442"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="rulebook-default",
                models="translate-default",
                symbols="aeon-core",
                glossary="aeon-core",
            ),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(profile_id="test", provider="gemini", model="gemini-2.0-flash"),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _create_simple_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello World", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


class TestResolveDoc:
    """Unit tests for _resolve_doc."""

    def test_produces_hashes(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        doc_plan = _resolve_doc(ctx)

        assert doc_plan.doc_id == "test-doc"
        assert doc_plan.source_pdf_path == str(pdf)
        assert len(doc_plan.config_hash) == 64  # SHA-256 hex
        assert len(doc_plan.rule_profile_hash) == 64
        assert len(doc_plan.model_profile_hash) == 64
        assert len(doc_plan.symbol_pack_hash) == 64
        assert len(doc_plan.glossary_pack_hash) == 64
        assert doc_plan.patch_set_hash is None  # no patch set

    def test_hashes_are_deterministic(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        plan1 = _resolve_doc(ctx)
        plan2 = _resolve_doc(ctx)

        assert plan1.config_hash == plan2.config_hash
        assert plan1.rule_profile_hash == plan2.rule_profile_hash
        assert plan1.model_profile_hash == plan2.model_profile_hash

    def test_different_configs_produce_different_hashes(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        plan1 = _resolve_doc(ctx)

        # Change glossary pack version
        ctx.glossary_pack = GlossaryPack(pack_id="test", version="2.0.0")
        plan2 = _resolve_doc(ctx)

        assert plan1.glossary_pack_hash != plan2.glossary_pack_hash
        assert plan1.config_hash == plan2.config_hash  # doc config unchanged

    def test_missing_pdf_raises(self, tmp_path: Path) -> None:
        missing_pdf = tmp_path / "nonexistent.pdf"
        ctx = _make_context(tmp_path, missing_pdf)

        import pytest

        with pytest.raises(FileNotFoundError, match="Source PDF not found"):
            _resolve_doc(ctx)


class TestHashPromptBundle:
    """Tests for prompt bundle hashing."""

    def test_hashes_existing_bundle(self, tmp_path: Path) -> None:
        configs_root = tmp_path / "configs"
        configs_root.mkdir()
        bundle_dir = tmp_path / "prompts" / "translate" / "v1"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "system.j2").write_text("Translate {{ source_locale }}.")
        (bundle_dir / "schema.json").write_text("{}")

        result = _hash_prompt_bundle(configs_root, "translate-v1")
        assert result is not None
        assert len(result) == 64

    def test_returns_none_for_missing_bundle(self, tmp_path: Path) -> None:
        configs_root = tmp_path / "configs"
        configs_root.mkdir()

        result = _hash_prompt_bundle(configs_root, "translate-v99")
        assert result is None

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        configs_root = tmp_path / "configs"
        configs_root.mkdir()
        bundle_dir = tmp_path / "prompts" / "translate" / "v1"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "system.j2").write_text("Translate.")

        h1 = _hash_prompt_bundle(configs_root, "translate-v1")
        h2 = _hash_prompt_bundle(configs_root, "translate-v1")
        assert h1 == h2


class TestResolveRunStage:
    """Integration tests for the full stage."""

    def test_writes_resolved_plan(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        ResolveRunStage().execute(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "resolve_run", "resolved_plan.json", ResolvedRunPlan
        )
        assert plan.run_id == "run-001"
        assert len(plan.docs) == 1
        assert plan.docs[0].doc_id == "test-doc"
        assert len(plan.stage_plan) > 0
        assert "resolve_run" in plan.stage_plan

    def test_config_snapshot_populated(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        ResolveRunStage().execute(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "resolve_run", "resolved_plan.json", ResolvedRunPlan
        )
        assert "pipeline" in plan.config_snapshot
        assert "document" in plan.config_snapshot
        assert plan.config_snapshot["document"]["doc_id"] == "test-doc"

    def test_stage_registration(self) -> None:
        stage = ResolveRunStage()
        assert stage.name == "resolve_run"
        assert stage.version == "1.0.0"
