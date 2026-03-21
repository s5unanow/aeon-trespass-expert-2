"""Tests for figure-caption spatial linking utility."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from aeon_reader_pipeline.models.evidence_models import (
    NormalizedBBox,
    PageRegionGraph,
    PrimitivePageEvidence,
    RegionCandidate,
    RegionConfidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.models.ir_models import (
    CaptionBlock,
    FigureBlock,
    PageRecord,
    TextRun,
)
from aeon_reader_pipeline.utils.figure_caption_linking import (
    apply_links_to_blocks,
    link_figures_captions_sequential,
    link_figures_captions_spatial,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _figure_region(
    region_id: str,
    bbox: NormalizedBBox,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="figure",
        bbox=bbox,
        confidence=RegionConfidence(value=0.8, reasons=["image_primitive"]),
    )


def _text_prim(
    primitive_id: str,
    bbox: NormalizedBBox,
    text: str,
) -> TextPrimitiveEvidence:
    return TextPrimitiveEvidence(
        primitive_id=primitive_id,
        bbox_norm=bbox,
        text=text,
    )


def _make_record(blocks: list) -> PageRecord:  # type: ignore[type-arg]
    return PageRecord(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        blocks=blocks,
    )


def _make_region_graph(
    regions: list[RegionCandidate],
) -> PageRegionGraph:
    return PageRegionGraph(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        regions=regions,
    )


def _make_primitive(
    text_primitives: list[TextPrimitiveEvidence],
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        text_primitives=text_primitives,
    )


# ---------------------------------------------------------------------------
# Unit tests — spatial scoring
# ---------------------------------------------------------------------------


class TestSpatialLinking:
    def test_single_figure_caption_below(self) -> None:
        """Basic case: one figure with its caption directly below."""
        fig = _figure_region("fig1", _bbox(0.1, 0.1, 0.5, 0.3))
        cap = _text_prim("txt1", _bbox(0.1, 0.32, 0.5, 0.36), "Figure 1: A diagram")

        region_graph = _make_region_graph([fig])
        primitive = _make_primitive([cap])
        record = _make_record(
            [
                FigureBlock(block_id="blk:fig1", asset_ref="img.png", source_block_index=900),
                CaptionBlock(
                    block_id="blk:cap1",
                    content=[TextRun(text="Figure 1: A diagram")],
                    source_block_index=1,
                ),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)

        assert result.method == "spatial"
        assert len(result.links) == 1
        link = result.links[0]
        assert link.figure_id == "fig1"
        assert link.caption_id == "txt1"
        assert link.score > 0.5
        assert link.x_overlap_ratio > 0.9
        assert link.figure_block_id == "blk:fig1"
        assert link.caption_block_id == "blk:cap1"

    def test_two_figures_disambiguated(self) -> None:
        """Two figures with two captions — spatial scoring pairs correctly."""
        # Figure A at top-left, caption A below it
        fig_a = _figure_region("figA", _bbox(0.05, 0.05, 0.45, 0.25))
        cap_a = _text_prim("capA", _bbox(0.05, 0.27, 0.45, 0.30), "Figure 1: First")

        # Figure B at bottom-right, caption B below it
        fig_b = _figure_region("figB", _bbox(0.55, 0.50, 0.95, 0.70))
        cap_b = _text_prim("capB", _bbox(0.55, 0.72, 0.95, 0.75), "Figure 2: Second")

        region_graph = _make_region_graph([fig_a, fig_b])
        primitive = _make_primitive([cap_a, cap_b])
        record = _make_record(
            [
                FigureBlock(block_id="blk:figA", asset_ref="a.png", source_block_index=900),
                CaptionBlock(
                    block_id="blk:capA",
                    content=[TextRun(text="Figure 1: First")],
                    source_block_index=1,
                ),
                FigureBlock(block_id="blk:figB", asset_ref="b.png", source_block_index=901),
                CaptionBlock(
                    block_id="blk:capB",
                    content=[TextRun(text="Figure 2: Second")],
                    source_block_index=2,
                ),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)

        assert len(result.links) == 2

        link_a = next(lnk for lnk in result.links if lnk.figure_id == "figA")
        link_b = next(lnk for lnk in result.links if lnk.figure_id == "figB")

        assert link_a.caption_block_id == "blk:capA"
        assert link_b.caption_block_id == "blk:capB"
        assert link_a.score > 0.5
        assert link_b.score > 0.5

    def test_caption_above_figure_still_links(self) -> None:
        """Caption positioned above figure should still be linked (lower score)."""
        cap = _text_prim("cap1", _bbox(0.1, 0.10, 0.5, 0.13), "Figure 1: Above")
        fig = _figure_region("fig1", _bbox(0.1, 0.15, 0.5, 0.35))

        region_graph = _make_region_graph([fig])
        primitive = _make_primitive([cap])
        record = _make_record(
            [
                CaptionBlock(
                    block_id="blk:cap1",
                    content=[TextRun(text="Figure 1: Above")],
                    source_block_index=0,
                ),
                FigureBlock(block_id="blk:fig1", asset_ref="img.png", source_block_index=900),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)

        assert len(result.links) == 1
        assert result.links[0].score > 0

    def test_no_captions_returns_empty(self) -> None:
        """Page with figures but no caption text returns no links."""
        fig = _figure_region("fig1", _bbox(0.1, 0.1, 0.5, 0.3))
        non_caption = _text_prim("txt1", _bbox(0.1, 0.35, 0.5, 0.38), "Just a paragraph")

        region_graph = _make_region_graph([fig])
        primitive = _make_primitive([non_caption])
        record = _make_record(
            [
                FigureBlock(block_id="blk:fig1", asset_ref="img.png", source_block_index=900),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)
        assert len(result.links) == 0

    def test_far_apart_rejected(self) -> None:
        """Figure and caption too far apart vertically are not linked."""
        fig = _figure_region("fig1", _bbox(0.1, 0.05, 0.5, 0.15))
        cap = _text_prim("cap1", _bbox(0.1, 0.85, 0.5, 0.88), "Figure 1: Far away")

        region_graph = _make_region_graph([fig])
        primitive = _make_primitive([cap])
        record = _make_record(
            [
                FigureBlock(block_id="blk:fig1", asset_ref="img.png", source_block_index=900),
                CaptionBlock(
                    block_id="blk:cap1",
                    content=[TextRun(text="Figure 1: Far away")],
                    source_block_index=1,
                ),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)
        assert len(result.links) == 0

    def test_exclusivity_one_caption_per_figure(self) -> None:
        """One figure with two nearby captions — only the best match wins."""
        fig = _figure_region("fig1", _bbox(0.1, 0.1, 0.5, 0.3))
        cap_close = _text_prim("cap_close", _bbox(0.1, 0.32, 0.5, 0.35), "Figure 1: Close")
        cap_far = _text_prim("cap_far", _bbox(0.1, 0.40, 0.5, 0.43), "Fig. 2: Farther")

        region_graph = _make_region_graph([fig])
        primitive = _make_primitive([cap_close, cap_far])
        record = _make_record(
            [
                FigureBlock(block_id="blk:fig1", asset_ref="img.png", source_block_index=900),
                CaptionBlock(
                    block_id="blk:cap_close",
                    content=[TextRun(text="Figure 1: Close")],
                    source_block_index=1,
                ),
                CaptionBlock(
                    block_id="blk:cap_far",
                    content=[TextRun(text="Fig. 2: Farther")],
                    source_block_index=2,
                ),
            ]
        )

        result = link_figures_captions_spatial(region_graph, primitive, record)

        assert len(result.links) == 1
        assert result.links[0].caption_block_id == "blk:cap_close"


# ---------------------------------------------------------------------------
# Unit tests — sequential fallback
# ---------------------------------------------------------------------------


class TestSequentialLinking:
    def test_basic_sequential(self) -> None:
        """Sequential linking pairs figures and captions positionally."""
        record = _make_record(
            [
                FigureBlock(block_id="fig1", asset_ref="img.png"),
                CaptionBlock(
                    block_id="cap1",
                    content=[TextRun(text="Figure 1: Test")],
                ),
            ]
        )

        result = link_figures_captions_sequential(record)

        assert result.method == "sequential"
        assert len(result.links) == 1
        assert result.links[0].figure_block_id == "fig1"
        assert result.links[0].caption_block_id == "cap1"
        assert result.links[0].score > 0.5

    def test_figure_first_ordering_links_correctly(self) -> None:
        """Figures before captions (pipeline ordering) are matched positionally."""
        record = _make_record(
            [
                FigureBlock(block_id="fig1", asset_ref="a.png"),
                FigureBlock(block_id="fig2", asset_ref="b.png"),
                FigureBlock(block_id="fig3", asset_ref="c.png"),
                CaptionBlock(block_id="cap1", content=[TextRun(text="Figure 1")]),
                CaptionBlock(block_id="cap2", content=[TextRun(text="Figure 2")]),
                CaptionBlock(block_id="cap3", content=[TextRun(text="Figure 3")]),
            ]
        )

        result = link_figures_captions_sequential(record)

        assert len(result.links) == 3
        assert result.links[0].figure_block_id == "fig1"
        assert result.links[0].caption_block_id == "cap1"
        assert result.links[1].figure_block_id == "fig2"
        assert result.links[1].caption_block_id == "cap2"
        assert result.links[2].figure_block_id == "fig3"
        assert result.links[2].caption_block_id == "cap3"

    def test_more_figures_than_captions(self) -> None:
        """Extra figures without captions are unlinked (no crash)."""
        record = _make_record(
            [
                FigureBlock(block_id="fig1", asset_ref="a.png"),
                FigureBlock(block_id="fig2", asset_ref="b.png"),
                CaptionBlock(block_id="cap1", content=[TextRun(text="Figure 1")]),
            ]
        )

        result = link_figures_captions_sequential(record)

        assert len(result.links) == 1
        assert result.links[0].figure_block_id == "fig1"
        assert result.links[0].caption_block_id == "cap1"


# ---------------------------------------------------------------------------
# Unit tests — apply_links_to_blocks
# ---------------------------------------------------------------------------


class TestApplyLinks:
    def test_apply_sets_block_ids(self) -> None:
        """Applying links sets caption_block_id and parent_block_id."""
        from aeon_reader_pipeline.models.evidence_models import (
            FigureCaptionLink,
            PageFigureCaptionLinks,
        )

        record = _make_record(
            [
                FigureBlock(block_id="fig1", asset_ref="img.png"),
                CaptionBlock(block_id="cap1", content=[TextRun(text="Figure 1")]),
            ]
        )

        links = PageFigureCaptionLinks(
            page_number=1,
            doc_id="test-doc",
            links=[
                FigureCaptionLink(
                    figure_id="fig1",
                    caption_id="cap1",
                    figure_block_id="fig1",
                    caption_block_id="cap1",
                    score=0.9,
                ),
            ],
        )

        updated = apply_links_to_blocks(record, links)

        fig = next(b for b in updated.blocks if isinstance(b, FigureBlock))
        cap = next(b for b in updated.blocks if isinstance(b, CaptionBlock))
        assert fig.caption_block_id == "cap1"
        assert cap.parent_block_id == "fig1"

    def test_apply_noop_without_block_ids(self) -> None:
        """Links without resolved block IDs do not modify blocks."""
        from aeon_reader_pipeline.models.evidence_models import (
            FigureCaptionLink,
            PageFigureCaptionLinks,
        )

        record = _make_record(
            [
                FigureBlock(block_id="fig1", asset_ref="img.png"),
            ]
        )

        links = PageFigureCaptionLinks(
            page_number=1,
            doc_id="test-doc",
            links=[
                FigureCaptionLink(
                    figure_id="reg:1:0",
                    caption_id="txt:1:0",
                    score=0.5,
                ),
            ],
        )

        updated = apply_links_to_blocks(record, links)
        fig = next(b for b in updated.blocks if isinstance(b, FigureBlock))
        assert fig.caption_block_id is None


# ---------------------------------------------------------------------------
# Integration: full pipeline with nontrivial layout
# ---------------------------------------------------------------------------


def _create_single_figure_pdf(path: Path) -> None:
    """Create a PDF with one figure and its caption for integration testing."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 50), "Content Title", fontsize=18, fontname="hebo")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0)
    pix.set_rect(pix.irect, (100, 100, 200))
    page.insert_image(pymupdf.Rect(72, 100, 200, 200), pixmap=pix)
    page.insert_text((72, 220), "Figure 1: Test diagram", fontsize=10, fontname="heit")
    page.insert_text((72, 260), "After the figure.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


class TestIntegrationLinkageArtifact:
    def test_linkage_artifact_persisted(self, tmp_path: Path) -> None:
        """The pipeline persists a figure-caption linkage artifact with scores."""
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
        from aeon_reader_pipeline.stage_framework.context import StageContext
        from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
        from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
        from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
        from aeon_reader_pipeline.stages.resolve_assets_symbols import (
            ResolveAssetsSymbolsStage,
        )

        pdf = tmp_path / "figure.pdf"
        _create_single_figure_pdf(pdf)

        configs_root = pdf.parent / "configs"
        configs_root.mkdir(exist_ok=True)
        store = ArtifactStore(tmp_path / "artifacts")
        store.create_run("run-001", ["test-doc"])

        ctx = StageContext(
            run_id="run-001",
            doc_id="test-doc",
            pipeline_config=PipelineConfig(run_id="run-001"),
            document_config=DocumentConfig(
                doc_id="test-doc",
                slug="test-doc",
                source_pdf=str(pdf),
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
            model_profile=ModelProfile(
                profile_id="test", provider="gemini", model="gemini-2.0-flash"
            ),
            symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
            glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
            patch_set=None,
            artifact_store=store,
            configs_root=configs_root,
        )

        IngestSourceStage().execute(ctx)
        ExtractPrimitivesStage().execute(ctx)
        NormalizeLayoutStage().execute(ctx)
        ResolveAssetsSymbolsStage().execute(ctx)

        # The linkage artifact should be persisted
        from aeon_reader_pipeline.models.evidence_models import PageFigureCaptionLinks

        link_artifact = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "pages/p0001_figure_caption_links.json",
            PageFigureCaptionLinks,
        )
        assert link_artifact.method == "sequential"
        assert len(link_artifact.links) >= 1

        link = link_artifact.links[0]
        assert link.score > 0
        assert len(link.reasons) > 0
        assert link.figure_block_id != ""
        assert link.caption_block_id != ""

        # The blocks should also have the links applied
        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "pages/p0001.json",
            PageRecord,
        )
        figures = [b for b in record.blocks if isinstance(b, FigureBlock)]
        captions = [b for b in record.blocks if isinstance(b, CaptionBlock)]

        assert len(figures) >= 1
        assert figures[0].caption_block_id is not None
        if captions:
            assert captions[0].parent_block_id == figures[0].block_id
