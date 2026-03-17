"""Tests for the plan_translation stage."""

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
    GlossaryTermEntry,
    ModelProfile,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.ir_models import (
    HeadingBlock,
    ListBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.models.translation_models import (
    TranslationPlan,
    TranslationPlanSummary,
    TranslationUnit,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import (
    PlanTranslationStage,
    _collect_text_nodes,
    _find_relevant_glossary,
    _plan_page,
)
from aeon_reader_pipeline.stages.resolve_assets_symbols import ResolveAssetsSymbolsStage
from aeon_reader_pipeline.utils.ids import block_id, inline_id


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
    glossary_terms: list[GlossaryTermEntry] | None = None,
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
        glossary_pack=GlossaryPack(
            pack_id="test",
            version="1.0.0",
            terms=glossary_terms or [],
        ),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _create_heading_body_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Title", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text here.", fontsize=11, fontname="helv")
    page.insert_text(
        (72, 150), "Another paragraph with more content.", fontsize=11, fontname="helv"
    )
    doc.save(str(path))
    doc.close()


def _run_through_plan(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)


class TestPlanTranslationUnit:
    """Unit tests for planner helpers."""

    def test_collect_text_nodes_from_paragraph(self) -> None:
        bid = block_id("doc", 1, 0, "paragraph")
        block = ParagraphBlock(
            block_id=bid,
            content=[TextRun(text="Hello world"), TextRun(text="Second run")],
        )
        nodes = _collect_text_nodes(block, bid)
        # All TextRuns in a block are merged into one TextNode
        assert len(nodes) == 1
        assert nodes[0].inline_id == inline_id(bid, 0)
        assert nodes[0].source_text == "Hello world Second run"

    def test_collect_text_nodes_from_list(self) -> None:
        from aeon_reader_pipeline.models.ir_models import ListItemBlock

        bid = block_id("doc", 1, 0, "list")
        items = [
            ListItemBlock(
                block_id=f"{bid}:li00",
                bullet="-",
                content=[TextRun(text="First item")],
            ),
            ListItemBlock(
                block_id=f"{bid}:li01",
                bullet="-",
                content=[TextRun(text="Second item")],
            ),
        ]
        block = ListBlock(block_id=bid, items=items)
        nodes = _collect_text_nodes(block, bid)
        assert len(nodes) == 2
        assert "First item" in nodes[0].source_text

    def test_collect_text_nodes_skips_empty(self) -> None:
        bid = block_id("doc", 1, 0, "paragraph")
        block = ParagraphBlock(
            block_id=bid,
            content=[TextRun(text=""), TextRun(text="  "), TextRun(text="Real text")],
        )
        nodes = _collect_text_nodes(block, bid)
        assert len(nodes) == 1

    def test_find_relevant_glossary(self) -> None:
        from aeon_reader_pipeline.models.translation_models import TextNode

        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                lock_translation=True,
            ),
            GlossaryTermEntry(
                term_id="t2",
                en_canonical="Shield",
                ru_preferred="\u0429\u0438\u0442",
            ),
        ]
        pack = GlossaryPack(pack_id="test", version="1.0.0", terms=terms)
        nodes = [TextNode(inline_id="i1", source_text="The Titan attacks")]

        hints = _find_relevant_glossary(nodes, pack, "test-doc")
        assert len(hints) == 1
        assert hints[0].en == "Titan"
        assert hints[0].locked is True

    def test_find_glossary_respects_doc_scope(self) -> None:
        from aeon_reader_pipeline.models.translation_models import TextNode

        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                doc_scope=["other-doc"],
            ),
        ]
        pack = GlossaryPack(pack_id="test", version="1.0.0", terms=terms)
        nodes = [TextNode(inline_id="i1", source_text="The Titan attacks")]

        hints = _find_relevant_glossary(nodes, pack, "test-doc")
        assert len(hints) == 0

    def test_plan_page_skips_facsimile(self) -> None:
        record = PageRecord(
            page_number=1,
            doc_id="test-doc",
            width_pt=612,
            height_pt=792,
            render_mode="facsimile",
            blocks=[
                ParagraphBlock(
                    block_id="b1",
                    content=[TextRun(text="Should be skipped")],
                )
            ],
        )
        pack = GlossaryPack(pack_id="test", version="1.0.0")
        units = _plan_page(record, "test-doc", pack)
        assert len(units) == 0

    def test_plan_page_creates_units(self) -> None:
        record = PageRecord(
            page_number=1,
            doc_id="test-doc",
            width_pt=612,
            height_pt=792,
            blocks=[
                HeadingBlock(
                    block_id="test-doc:p0001:b000:heading",
                    level=1,
                    content=[TextRun(text="Title")],
                ),
                ParagraphBlock(
                    block_id="test-doc:p0001:b001:paragraph",
                    content=[TextRun(text="Body text here.")],
                ),
            ],
        )
        pack = GlossaryPack(pack_id="test", version="1.0.0")
        units = _plan_page(record, "test-doc", pack)
        assert len(units) >= 2  # heading gets its own unit
        assert units[0].style_hint == "heading"

    def test_unit_ids_are_deterministic(self) -> None:
        record = PageRecord(
            page_number=3,
            doc_id="test-doc",
            width_pt=612,
            height_pt=792,
            blocks=[
                ParagraphBlock(
                    block_id="test-doc:p0003:b000:paragraph",
                    content=[TextRun(text="Some text")],
                ),
            ],
        )
        pack = GlossaryPack(pack_id="test", version="1.0.0")
        units1 = _plan_page(record, "test-doc", pack)
        units2 = _plan_page(record, "test-doc", pack)
        assert units1[0].unit_id == units2[0].unit_id
        assert units1[0].source_fingerprint == units2[0].source_fingerprint


class TestPlanTranslationIntegration:
    """Integration tests running through the full pipeline."""

    def test_plan_produces_units(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "translation_plan.json", TranslationPlan
        )
        assert plan.total_units > 0
        assert plan.total_text_nodes > 0
        assert len(plan.units) == plan.total_units

    def test_plan_writes_individual_unit_files(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "translation_plan.json", TranslationPlan
        )
        for unit in plan.units:
            loaded = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "plan_translation",
                f"units/{unit.unit_id}.json",
                TranslationUnit,
            )
            assert loaded.unit_id == unit.unit_id

    def test_plan_summary(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "summary.json", TranslationPlanSummary
        )
        assert summary.total_units > 0
        assert summary.page_count == 1

    def test_plan_with_glossary(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        terms = [
            GlossaryTermEntry(
                term_id="t-chapter",
                en_canonical="Chapter",
                ru_preferred="\u0413\u043b\u0430\u0432\u0430",
                lock_translation=True,
            ),
        ]
        ctx = _make_context(tmp_path, pdf, glossary_terms=terms)
        _run_through_plan(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "translation_plan.json", TranslationPlan
        )
        # At least one unit should have the glossary hint
        units_with_glossary = [u for u in plan.units if u.glossary_subset]
        assert len(units_with_glossary) >= 1

    def test_stage_registration(self) -> None:
        stage = PlanTranslationStage()
        assert stage.name == "plan_translation"
        assert stage.version == "1.0.0"

    def test_fixture_simple_text(self, tmp_path: Path) -> None:
        pdf = Path(__file__).parent.parent / "fixtures" / "pdf" / "simple_text.pdf"
        assert pdf.exists()
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "translation_plan.json", TranslationPlan
        )
        assert plan.total_units > 0
        # Should have units from both pages
        pages = {u.page_number for u in plan.units}
        assert 1 in pages
        assert 2 in pages
