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
    DocumentFurnitureProfile,
    NormalizedBBox,
    PageReadingOrder,
    PageRegionGraph,
    ReadingOrderEntry,
    RegionCandidate,
    RegionConfidence,
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
        assert stage.version == "0.5.0"

    def test_resolve_page_ir_registration(self) -> None:
        stage = ResolvePageIRStage()
        assert stage.name == "resolve_page_ir"
        assert stage.version == "0.2.0"


class TestEvidencePipeline:
    def test_collect_evidence_does_not_skip(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        assert CollectEvidenceStage().should_skip(ctx) is False

    def test_collect_evidence_produces_canonical(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
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
        ctx = _make_context(tmp_path, pdf)
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
        assert resolved.page_confidence > 0.0
        assert resolved.fallback_image_ref is None

    def test_resolve_page_ir_sets_fallback_image_ref_for_non_semantic(self, tmp_path: Path) -> None:
        """Non-semantic routes must carry a fallback image reference."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        # Overwrite canonical evidence with extreme penalties to force facsimile
        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        unit_bbox = NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)
        low_conf = canonical.model_copy(
            update={
                "estimated_column_count": 3,
                "has_tables": True,
                "has_figures": True,
                "has_callouts": True,
                "furniture_fraction": 0.9,
                "region_graph": PageRegionGraph(
                    page_number=1,
                    doc_id="test-doc",
                    width_pt=612.0,
                    height_pt=792.0,
                    regions=[
                        RegionCandidate(
                            region_id="r1",
                            kind_hint="main_flow",
                            bbox=unit_bbox,
                            confidence=RegionConfidence(value=0.0),
                        )
                    ],
                ),
                "reading_order": PageReadingOrder(
                    page_number=1,
                    doc_id="test-doc",
                    entries=[
                        ReadingOrderEntry(
                            sequence_index=0,
                            region_id="r1",
                            kind_hint="main_flow",
                            confidence=RegionConfidence(value=0.0),
                        )
                    ],
                    total_regions=5,
                    unassigned_region_ids=["r2", "r3", "r4", "r5"],
                ),
            }
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            low_conf,
        )

        ResolvePageIRStage().execute(ctx)

        resolved = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_page_ir",
            "resolved/p0001.json",
            ResolvedPageIR,
        )
        assert resolved.render_mode != "semantic"
        assert resolved.fallback_image_ref == "p0001_fallback.png"

    def test_full_pipeline_produces_page_record(self, tmp_path: Path) -> None:
        """Extract → collect_evidence → resolve_page_ir → normalize produces PageRecord."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)
        ResolvePageIRStage().execute(ctx)
        NormalizeLayoutStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert record.page_number == 1
        assert len(record.blocks) > 0

    def test_furniture_profile_emitted(self, tmp_path: Path) -> None:
        """collect_evidence emits a DocumentFurnitureProfile artifact."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        profile = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/furniture_profile.json",
            DocumentFurnitureProfile,
        )
        assert profile.doc_id == "test-doc"
        assert profile.total_pages_analyzed == 1
        # Single page → no furniture detected
        assert profile.furniture_candidates == []

    def test_canonical_has_furniture_fields(self, tmp_path: Path) -> None:
        """Canonical evidence includes furniture_ids and template_id fields."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        # Single page: no furniture, empty fields
        assert canonical.furniture_ids == []
        assert canonical.template_id == ""
        assert canonical.furniture_fraction == 0.0

    def test_has_tables_detected(self, tmp_path: Path) -> None:
        """Canonical evidence reflects table presence from region graph."""
        pdf = tmp_path / "source.pdf"
        # Simple PDF without tables
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
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

    def test_summary_flags_derived_from_region_graph(self, tmp_path: Path) -> None:
        """Summary flags are derived from region graph, not raw primitive counts."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_extract(ctx)
        CollectEvidenceStage().execute(ctx)

        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            "evidence/p0001_canonical.json",
            CanonicalPageEvidence,
        )
        # Text-only PDF: no figure/table/callout regions in graph
        assert canonical.has_figures is False
        assert canonical.has_tables is False
        assert canonical.has_callouts is False

        # Verify consistency: region graph should have no figure/table/callout regions
        assert canonical.region_graph is not None
        region_kinds = {r.kind_hint for r in canonical.region_graph.regions}
        assert ("figure" in region_kinds) == canonical.has_figures
        assert ("table" in region_kinds) == canonical.has_tables
        assert ("callout" in region_kinds) == canonical.has_callouts

    def test_evidence_hashes_are_deterministic(self, tmp_path: Path) -> None:
        """Running twice produces the same hashes."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)

        # First run
        ctx1 = _make_context(tmp_path / "run1", pdf, run_id="run-a")
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
        ctx2 = _make_context(tmp_path / "run2", pdf, run_id="run-b")
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
