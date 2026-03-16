"""Tests for the normalize_layout stage."""

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
from aeon_reader_pipeline.models.ir_models import (
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    ListBlock,
    PageRecord,
    ParagraphBlock,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage


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


def _run_through_normalize(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)


def _create_heading_body_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Title", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text here.", fontsize=11, fontname="helv")
    page.insert_text((72, 150), "Another paragraph.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _create_list_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Section Header", fontsize=16, fontname="hebo")
    y = 110
    for item in ["- First bullet item", "- Second bullet item", "- Third bullet item"]:
        page.insert_text((72, y), item, fontsize=11, fontname="helv")
        y += 20
    page.insert_text((72, y + 10), "After the list.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _create_figure_caption_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Content with Figure", fontsize=16, fontname="hebo")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0)
    pix.set_rect(pix.irect, (100, 100, 200))
    page.insert_image(pymupdf.Rect(72, 100, 200, 200), pixmap=pix)
    page.insert_text((72, 220), "Figure 1: Test diagram", fontsize=10, fontname="heit")
    page.insert_text((72, 250), "Text after the caption.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


class TestNormalizeLayout:
    def test_produces_page_records(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert record.page_number == 1
        assert record.doc_id == "test-doc"
        assert len(record.blocks) > 0

    def test_heading_detected(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        headings = [b for b in record.blocks if isinstance(b, HeadingBlock)]
        assert len(headings) >= 1
        h = headings[0]
        heading_text = " ".join(run.text for run in h.content)
        assert "Chapter Title" in heading_text

    def test_paragraphs_detected(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        paragraphs = [b for b in record.blocks if isinstance(b, ParagraphBlock)]
        assert len(paragraphs) >= 1

    def test_list_detection(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_list_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        lists = [b for b in record.blocks if isinstance(b, ListBlock)]
        assert len(lists) >= 1
        assert len(lists[0].items) == 3

    def test_figure_detected(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_figure_caption_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        figures = [b for b in record.blocks if isinstance(b, FigureBlock)]
        assert len(figures) >= 1

    def test_caption_detected(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_figure_caption_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        captions = [b for b in record.blocks if isinstance(b, CaptionBlock)]
        assert len(captions) >= 1
        caption_text = " ".join(run.text for run in captions[0].content)
        assert "Figure 1" in caption_text

    def test_anchors_from_headings(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert len(record.anchors) >= 1
        assert record.anchors[0].label != ""

    def test_fingerprint_populated(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_heading_body_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert len(record.fingerprint) == 16

    def test_block_ids_unique(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_list_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        all_ids: list[str] = []
        for b in record.blocks:
            all_ids.append(b.block_id)
            if isinstance(b, ListBlock):
                for item in b.items:
                    all_ids.append(item.block_id)
        assert len(all_ids) == len(set(all_ids)), "Block IDs must be unique"

    def test_stage_registration(self) -> None:
        stage = NormalizeLayoutStage()
        assert stage.name == "normalize_layout"
        assert stage.version == "1.0.0"

    def test_fixture_simple_text(self, tmp_path: Path) -> None:
        """Normalize the shared simple_text fixture PDF."""
        pdf = Path(__file__).parent.parent / "fixtures" / "pdf" / "simple_text.pdf"
        assert pdf.exists()
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        for pn in (1, 2):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "normalize_layout",
                f"pages/p{pn:04d}.json",
                PageRecord,
            )
            headings = [b for b in record.blocks if isinstance(b, HeadingBlock)]
            paragraphs = [b for b in record.blocks if isinstance(b, ParagraphBlock)]
            assert len(headings) >= 1, f"Page {pn} should have a heading"
            assert len(paragraphs) >= 1, f"Page {pn} should have paragraphs"

    def test_fixture_multiformat(self, tmp_path: Path) -> None:
        """Normalize the multiformat fixture PDF."""
        pdf = Path(__file__).parent.parent / "fixtures" / "pdf" / "multiformat.pdf"
        assert pdf.exists()
        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        kinds = {b.kind for b in record.blocks}
        assert "heading" in kinds
        assert "list" in kinds
        assert "paragraph" in kinds
