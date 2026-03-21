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
from aeon_reader_pipeline.models.evidence_models import (
    NormalizedBBox,
    RegionCandidate,
    RegionConfidence,
)
from aeon_reader_pipeline.models.extract_models import (
    BBox,
    ExtractedPage,
    FontInfo,
    TextBlock,
    TextLine,
    TextSpan,
)
from aeon_reader_pipeline.models.ir_models import (
    Block,
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    ListBlock,
    ListItemBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import (
    NormalizeLayoutStage,
    _wrap_callout_blocks,
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
        assert stage.version == "1.1.0"

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

    def test_short_labels_not_merged(self, tmp_path: Path) -> None:
        """Short UI labels like 'Contents' and 'Skills' must stay as separate blocks."""
        pdf = tmp_path / "source.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        # Heading at larger font
        page.insert_text((72, 72), "Chapter One", fontsize=20, fontname="hebo")
        # Short UI labels at body font — these must NOT be merged
        page.insert_text((72, 120), "Contents", fontsize=11, fontname="helv")
        page.insert_text((72, 145), "Body paragraph that follows.", fontsize=11, fontname="helv")
        page.insert_text((72, 175), "Skills", fontsize=11, fontname="helv")
        page.insert_text((72, 200), "Another body paragraph here.", fontsize=11, fontname="helv")
        doc.save(str(pdf))
        doc.close()

        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        # Extract all paragraph texts
        para_texts = []
        for b in record.blocks:
            if isinstance(b, ParagraphBlock):
                text = " ".join(n.text for n in b.content if isinstance(n, TextRun))
                para_texts.append(text)

        # "Contents" and "Skills" must each be their own paragraph, not merged
        assert any(t == "Contents" for t in para_texts), (
            f"'Contents' should be a standalone paragraph, got: {para_texts}"
        )
        assert any(t == "Skills" for t in para_texts), (
            f"'Skills' should be a standalone paragraph, got: {para_texts}"
        )

    def test_allcaps_labels_not_merged(self, tmp_path: Path) -> None:
        """All-caps game terms like 'RHETORIC' must stay as separate blocks."""
        pdf = tmp_path / "source.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "Game Mechanics", fontsize=20, fontname="hebo")
        page.insert_text((72, 120), "IMPRISONMENT", fontsize=11, fontname="helv")
        page.insert_text((72, 145), "A player may be imprisoned.", fontsize=11, fontname="helv")
        doc.save(str(pdf))
        doc.close()

        ctx = _make_context(tmp_path, pdf)
        _run_through_normalize(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        para_texts = []
        for b in record.blocks:
            if isinstance(b, ParagraphBlock):
                text = " ".join(n.text for n in b.content if isinstance(n, TextRun))
                para_texts.append(text)

        assert any(t == "IMPRISONMENT" for t in para_texts), (
            f"'IMPRISONMENT' should be a standalone paragraph, got: {para_texts}"
        )

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


# ---------------------------------------------------------------------------
# Callout block wrapping tests (S5U-262)
# ---------------------------------------------------------------------------


def _make_text_block(
    block_index: int,
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    font_size: float = 11.0,
) -> TextBlock:
    """Create a synthetic TextBlock with one span."""
    return TextBlock(
        block_index=block_index,
        lines=[
            TextLine(
                spans=[
                    TextSpan(
                        text=text,
                        font=FontInfo(name="helv", size=font_size),
                        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    ),
                ],
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            )
        ],
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
    )


def _make_extracted_page(text_blocks: list[TextBlock]) -> ExtractedPage:
    return ExtractedPage(
        page_number=1,
        width_pt=612.0,
        height_pt=792.0,
        text_blocks=text_blocks,
        doc_id="test-doc",
    )


def _make_callout_region(
    region_id: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="callout",
        bbox=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        confidence=RegionConfidence(value=0.7, reasons=["drawing_encloses_text"]),
    )


class TestCalloutBlockWrapping:
    def test_blocks_within_callout_wrapped(self) -> None:
        """Text blocks inside a callout region are wrapped into a CalloutBlock."""
        # Page with one block outside and two blocks inside a callout box
        text_blocks = [
            _make_text_block(0, "Outside text", 72, 72, 540, 90),
            _make_text_block(1, "Inside line one", 100, 200, 500, 220),
            _make_text_block(2, "Inside line two", 100, 230, 500, 250),
        ]
        page = _make_extracted_page(text_blocks)

        # Callout region covers blocks 1 and 2 (in normalized coords)
        # Block 1: center ~= (300/612, 210/792) ≈ (0.49, 0.27)
        # Block 2: center ~= (300/612, 240/792) ≈ (0.49, 0.30)
        callout = _make_callout_region("reg:1:5", 0.10, 0.20, 0.90, 0.40)

        # Pre-classify all blocks as paragraphs
        blocks = [
            ParagraphBlock(
                block_id=f"b:{i}",
                content=[TextRun(text=tb.text)],
                source_block_index=tb.block_index,
            )
            for i, tb in enumerate(text_blocks)
        ]

        result = _wrap_callout_blocks(blocks, page, [callout], "test-doc")

        # Should have 2 blocks: outside paragraph + callout
        assert len(result) == 2
        outside = [b for b in result if isinstance(b, ParagraphBlock)]
        callouts = [b for b in result if isinstance(b, CalloutBlock)]
        assert len(outside) == 1
        assert len(callouts) == 1
        # Callout should contain text from both inside blocks
        callout_text = " ".join(n.text for n in callouts[0].content if isinstance(n, TextRun))
        assert "Inside line one" in callout_text
        assert "Inside line two" in callout_text

    def test_no_callout_regions_passthrough(self) -> None:
        """When no callout regions exist, all blocks pass through unchanged."""
        text_blocks = [
            _make_text_block(0, "Regular text", 72, 72, 540, 90),
        ]
        page = _make_extracted_page(text_blocks)
        blocks = [
            ParagraphBlock(
                block_id="b:0",
                content=[TextRun(text="Regular text")],
                source_block_index=0,
            ),
        ]

        result = _wrap_callout_blocks(blocks, page, [], "test-doc")
        assert len(result) == 1
        assert isinstance(result[0], ParagraphBlock)

    def test_block_outside_callout_not_wrapped(self) -> None:
        """Blocks whose center falls outside the callout region are not wrapped."""
        text_blocks = [
            _make_text_block(0, "Outside text", 72, 72, 540, 90),
        ]
        page = _make_extracted_page(text_blocks)

        # Callout region is far below the text block
        callout = _make_callout_region("reg:1:5", 0.10, 0.50, 0.90, 0.80)

        blocks = [
            ParagraphBlock(
                block_id="b:0",
                content=[TextRun(text="Outside text")],
                source_block_index=0,
            ),
        ]

        result = _wrap_callout_blocks(blocks, page, [callout], "test-doc")
        assert len(result) == 1
        assert isinstance(result[0], ParagraphBlock)

    def test_callout_block_has_correct_kind(self) -> None:
        """Wrapped callout blocks have kind='callout' and callout_type='note'."""
        text_blocks = [_make_text_block(0, "Box content", 100, 200, 500, 220)]
        page = _make_extracted_page(text_blocks)
        callout = _make_callout_region("reg:1:0", 0.10, 0.20, 0.90, 0.40)
        blocks = [
            ParagraphBlock(
                block_id="b:0",
                content=[TextRun(text="Box content")],
                source_block_index=0,
            ),
        ]

        result = _wrap_callout_blocks(blocks, page, [callout], "test-doc")
        assert len(result) == 1
        cb = result[0]
        assert isinstance(cb, CalloutBlock)
        assert cb.kind == "callout"
        assert cb.callout_type == "note"

    def test_list_block_content_preserved_in_callout(self) -> None:
        """ListBlock items inside a callout are preserved as inline content."""
        text_blocks = [
            _make_text_block(0, "- Item one", 100, 200, 500, 220),
            _make_text_block(1, "- Item two", 100, 230, 500, 250),
        ]
        page = _make_extracted_page(text_blocks)
        callout = _make_callout_region("reg:1:0", 0.10, 0.20, 0.90, 0.40)

        blocks: list[Block] = [
            ListBlock(
                block_id="b:list:0",
                items=[
                    ListItemBlock(
                        block_id="li:0",
                        bullet="-",
                        content=[TextRun(text="Item one")],
                        source_block_index=0,
                    ),
                    ListItemBlock(
                        block_id="li:1",
                        bullet="-",
                        content=[TextRun(text="Item two")],
                        source_block_index=1,
                    ),
                ],
                source_block_index=0,
            ),
        ]

        result = _wrap_callout_blocks(blocks, page, [callout], "test-doc")

        assert len(result) == 1
        cb = result[0]
        assert isinstance(cb, CalloutBlock)
        text = " ".join(n.text for n in cb.content if isinstance(n, TextRun))
        assert "Item one" in text
        assert "Item two" in text
