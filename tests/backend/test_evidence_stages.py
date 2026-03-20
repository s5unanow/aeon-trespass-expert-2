"""Tests for the evidence pipeline stages (collect_evidence, resolve_page_ir)."""

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
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    ResolvedPageIR,
)
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.collect_evidence import CollectEvidenceStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.resolve_page_ir import ResolvePageIRStage


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
    architecture: str = "v2",
) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id=run_id, architecture=architecture),  # type: ignore[arg-type]
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test", ru="Тест"),
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


def _create_test_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Title", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text here.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_extract(ctx: StageContext) -> None:
    """Run ingest + extract stages to produce primitive evidence."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)


class TestStageRegistration:
    def test_collect_evidence_registration(self) -> None:
        stage = CollectEvidenceStage()
        assert stage.name == "collect_evidence"
        assert stage.version == "0.1.0"

    def test_resolve_page_ir_registration(self) -> None:
        stage = ResolvePageIRStage()
        assert stage.name == "resolve_page_ir"
        assert stage.version == "0.1.0"


class TestV2SkipPath:
    def test_collect_evidence_skips_on_v2(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v2")
        assert CollectEvidenceStage().should_skip(ctx) is True

    def test_resolve_page_ir_skips_on_v2(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v2")
        assert ResolvePageIRStage().should_skip(ctx) is True

    def test_v2_normalize_works_unchanged(self, tmp_path: Path) -> None:
        """Legacy v2 path: extract → normalize produces PageRecord as before."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v2")
        _run_extract(ctx)
        NormalizeLayoutStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert record.page_number == 1
        assert len(record.blocks) > 0


class TestV3Path:
    def test_collect_evidence_does_not_skip_on_v3(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v3")
        # should_skip returns False for v3 (no cached manifest)
        assert CollectEvidenceStage().should_skip(ctx) is False

    def test_collect_evidence_produces_canonical(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v3")
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        assert canonical.page_number == 1
        assert canonical.doc_id == "test-doc"
        assert canonical.width_pt > 0
        assert canonical.height_pt > 0
        assert canonical.primitive_evidence_hash != ""
        assert canonical.estimated_column_count == 1

    def test_resolve_page_ir_produces_resolved(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v3")
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)
        ResolvePageIRStage().execute(ctx)

        resolved = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_page_ir",
            "resolved/p0001.json",
            ResolvedPageIR,
        )
        assert resolved.page_number == 1
        assert resolved.doc_id == "test-doc"
        assert resolved.canonical_evidence_hash != ""
        assert resolved.render_mode == "semantic"
        assert resolved.page_confidence == 1.0

    def test_v3_full_pipeline_produces_page_record(self, tmp_path: Path) -> None:
        """V3: extract → collect_evidence → resolve_page_ir → normalize produces PageRecord."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v3")
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)
        ResolvePageIRStage().execute(ctx)
        NormalizeLayoutStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert record.page_number == 1
        assert len(record.blocks) > 0

    def test_has_tables_detected(self, tmp_path: Path) -> None:
        """Canonical evidence reflects table presence from primitives."""
        pdf = tmp_path / "source.pdf"
        # Simple PDF without tables
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, architecture="v3")
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        assert canonical.has_tables is False

    def test_evidence_hashes_are_deterministic(self, tmp_path: Path) -> None:
        """Running twice produces the same hashes."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)

        # First run
        ctx1 = _make_context(tmp_path / "run1", pdf, architecture="v3", run_id="run-a")
        _run_extract(ctx1)
        CollectEvidenceStage().execute(ctx1)
        ResolvePageIRStage().execute(ctx1)

        c1 = ctx1.artifact_store.read_artifact(
            ctx1.run_id,
            ctx1.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        r1 = ctx1.artifact_store.read_artifact(
            ctx1.run_id,
            ctx1.doc_id,
            "resolve_page_ir",
            "resolved/p0001.json",
            ResolvedPageIR,
        )

        # Second run
        ctx2 = _make_context(tmp_path / "run2", pdf, architecture="v3", run_id="run-b")
        _run_extract(ctx2)
        CollectEvidenceStage().execute(ctx2)
        ResolvePageIRStage().execute(ctx2)

        c2 = ctx2.artifact_store.read_artifact(
            ctx2.run_id,
            ctx2.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        r2 = ctx2.artifact_store.read_artifact(
            ctx2.run_id,
            ctx2.doc_id,
            "resolve_page_ir",
            "resolved/p0001.json",
            ResolvedPageIR,
        )

        assert c1.primitive_evidence_hash == c2.primitive_evidence_hash
        assert r1.canonical_evidence_hash == r2.canonical_evidence_hash
