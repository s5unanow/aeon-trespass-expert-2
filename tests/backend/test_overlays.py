"""Tests for evidence overlay renderers."""

from __future__ import annotations

import pymupdf
import pytest

from aeon_reader_pipeline.models.evidence_models import (
    DocumentAssetRegistry,
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    FigureCaptionLink,
    FurnitureCandidate,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PageReadingOrder,
    PageRegionGraph,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    ReadingOrderEntry,
    RegionCandidate,
    RegionConfidence,
    ResolvedPageIR,
    SymbolCandidate,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.overlays import (
    render_assets_overlay,
    render_confidence_overlay,
    render_figure_caption_overlay,
    render_furniture_overlay,
    render_primitives_overlay,
    render_reading_order_overlay,
    render_regions_overlay,
    render_symbols_overlay,
)

_PNG_MAGIC = b"\x89PNG"
_MIN_SIZE = 1000

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pdf_page() -> pymupdf.Page:
    """Create a 1-page synthetic PDF and return its first page."""
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    return doc.load_page(0)


def _bbox(x0: float = 0.1, y0: float = 0.1, x1: float = 0.5, y1: float = 0.3) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


# ---------------------------------------------------------------------------
# Primitives overlay
# ---------------------------------------------------------------------------


class TestPrimitivesOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        evidence = PrimitivePageEvidence(
            page_number=1,
            doc_id="test",
            width_pt=612,
            height_pt=792,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000", bbox_norm=_bbox(), text="hello"
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=_bbox(0.5, 0.1, 0.9, 0.4),
                    content_hash="abc",
                ),
            ],
            table_primitives=[
                TablePrimitiveEvidence(
                    primitive_id="table:p0001:000",
                    bbox_norm=_bbox(0.1, 0.5, 0.9, 0.8),
                    rows=3,
                    cols=2,
                ),
            ],
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=_bbox(0.1, 0.85, 0.3, 0.95),
                ),
            ],
        )
        result = render_primitives_overlay(pdf_page, evidence)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_empty_evidence(self, pdf_page: pymupdf.Page) -> None:
        evidence = PrimitivePageEvidence(page_number=1, doc_id="test", width_pt=612, height_pt=792)
        result = render_primitives_overlay(pdf_page, evidence)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE


# ---------------------------------------------------------------------------
# Furniture overlay
# ---------------------------------------------------------------------------


class TestFurnitureOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        profile = DocumentFurnitureProfile(
            doc_id="test",
            total_pages_analyzed=5,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="f001",
                    furniture_type="header",
                    bbox_norm=_bbox(0.0, 0.0, 1.0, 0.05),
                    source_primitive_kind="text",
                    page_numbers=[1, 2, 3],
                ),
            ],
        )
        result = render_furniture_overlay(pdf_page, profile, page_number=1)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_skips_pages_not_in_list(self, pdf_page: pymupdf.Page) -> None:
        profile = DocumentFurnitureProfile(
            doc_id="test",
            total_pages_analyzed=5,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="f001",
                    furniture_type="footer",
                    bbox_norm=_bbox(0.0, 0.95, 1.0, 1.0),
                    source_primitive_kind="text",
                    page_numbers=[2, 3],
                ),
            ],
        )
        # Page 1 is not in the candidate's page_numbers
        result = render_furniture_overlay(pdf_page, profile, page_number=1)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Regions overlay
# ---------------------------------------------------------------------------


class TestRegionsOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612,
            height_pt=792,
            regions=[
                RegionCandidate(
                    region_id="r001",
                    kind_hint="main_flow",
                    bbox=_bbox(0.05, 0.1, 0.95, 0.9),
                    confidence=RegionConfidence(value=0.95, reasons=["good"]),
                ),
                RegionCandidate(
                    region_id="r002",
                    kind_hint="sidebar",
                    bbox=_bbox(0.7, 0.1, 0.95, 0.5),
                    confidence=RegionConfidence(value=0.7),
                ),
            ],
        )
        result = render_regions_overlay(pdf_page, graph)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_empty_regions(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(page_number=1, doc_id="test", width_pt=612, height_pt=792)
        result = render_regions_overlay(pdf_page, graph)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Reading order overlay
# ---------------------------------------------------------------------------


class TestReadingOrderOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612,
            height_pt=792,
            regions=[
                RegionCandidate(
                    region_id="r001",
                    kind_hint="column",
                    bbox=_bbox(0.05, 0.1, 0.45, 0.9),
                ),
                RegionCandidate(
                    region_id="r002",
                    kind_hint="column",
                    bbox=_bbox(0.55, 0.1, 0.95, 0.9),
                ),
            ],
        )
        reading_order = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[
                ReadingOrderEntry(
                    sequence_index=0,
                    region_id="r001",
                    kind_hint="column",
                    flow_role="main",
                ),
                ReadingOrderEntry(
                    sequence_index=1,
                    region_id="r002",
                    kind_hint="column",
                    flow_role="main",
                ),
            ],
            total_regions=2,
        )
        result = render_reading_order_overlay(pdf_page, graph, reading_order)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_missing_region_skipped(self, pdf_page: pymupdf.Page) -> None:
        """Entry referencing a missing region is silently skipped."""
        graph = PageRegionGraph(page_number=1, doc_id="test", width_pt=612, height_pt=792)
        reading_order = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="missing", kind_hint="column"),
            ],
            total_regions=0,
        )
        result = render_reading_order_overlay(pdf_page, graph, reading_order)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Assets overlay
# ---------------------------------------------------------------------------


class TestAssetsOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        from aeon_reader_pipeline.models.evidence_models import AssetClass, AssetOccurrence

        registry = DocumentAssetRegistry(
            doc_id="test",
            total_pages_analyzed=3,
            asset_classes=[
                AssetClass(
                    asset_class_id="asset:raster:000",
                    kind="raster",
                    occurrence_count=1,
                    page_numbers=[1],
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:000:p0001:00",
                            page_number=1,
                            bbox_norm=_bbox(0.2, 0.3, 0.6, 0.7),
                            source_primitive_id="image:p0001:000",
                            context_hint="figure",
                        ),
                    ],
                ),
            ],
            total_occurrences=1,
        )
        result = render_assets_overlay(pdf_page, registry, page_number=1)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_empty_registry(self, pdf_page: pymupdf.Page) -> None:
        registry = DocumentAssetRegistry(doc_id="test", total_pages_analyzed=1)
        result = render_assets_overlay(pdf_page, registry, page_number=1)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Symbols overlay
# ---------------------------------------------------------------------------


class TestSymbolsOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        cands = PageSymbolCandidates(
            page_number=1,
            doc_id="test",
            candidates=[
                SymbolCandidate(
                    candidate_id="sym:p0001:000",
                    page_number=1,
                    evidence_source="text_token",
                    bbox_norm=_bbox(0.1, 0.1, 0.15, 0.15),
                    symbol_id="sword",
                    confidence=0.9,
                    is_classified=True,
                ),
                SymbolCandidate(
                    candidate_id="sym:p0001:001",
                    page_number=1,
                    evidence_source="raster_hash",
                    bbox_norm=_bbox(0.2, 0.2, 0.25, 0.25),
                    confidence=0.6,
                    is_classified=True,
                    symbol_id="shield",
                ),
                SymbolCandidate(
                    candidate_id="sym:p0001:002",
                    page_number=1,
                    evidence_source="text_dingbat",
                    bbox_norm=_bbox(0.3, 0.3, 0.35, 0.35),
                    is_classified=False,
                ),
                SymbolCandidate(
                    candidate_id="sym:p0001:003",
                    page_number=1,
                    evidence_source="vector_signature",
                    bbox_norm=_bbox(0.4, 0.4, 0.45, 0.45),
                    is_decorative=True,
                ),
            ],
            classified_count=2,
            unclassified_count=2,
        )
        result = render_symbols_overlay(pdf_page, cands)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_empty_candidates(self, pdf_page: pymupdf.Page) -> None:
        cands = PageSymbolCandidates(page_number=1, doc_id="test")
        result = render_symbols_overlay(pdf_page, cands)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Figure-caption overlay
# ---------------------------------------------------------------------------


class TestFigureCaptionOverlay:
    def test_returns_valid_png(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612,
            height_pt=792,
            regions=[
                RegionCandidate(
                    region_id="fig1",
                    kind_hint="figure",
                    bbox=_bbox(0.1, 0.1, 0.9, 0.6),
                ),
                RegionCandidate(
                    region_id="cap1",
                    kind_hint="caption",
                    bbox=_bbox(0.1, 0.62, 0.9, 0.7),
                ),
            ],
        )
        links = [
            FigureCaptionLink(
                figure_id="fig1",
                caption_id="cap1",
                score=0.85,
                reasons=["spatial_proximity"],
            ),
        ]
        result = render_figure_caption_overlay(pdf_page, graph, links)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE

    def test_empty_links(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(page_number=1, doc_id="test", width_pt=612, height_pt=792)
        result = render_figure_caption_overlay(pdf_page, graph, [])
        assert result[:4] == _PNG_MAGIC

    def test_missing_region_handled(self, pdf_page: pymupdf.Page) -> None:
        graph = PageRegionGraph(page_number=1, doc_id="test", width_pt=612, height_pt=792)
        links = [
            FigureCaptionLink(figure_id="missing_fig", caption_id="missing_cap", score=0.5),
        ]
        result = render_figure_caption_overlay(pdf_page, graph, links)
        assert result[:4] == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Confidence overlay
# ---------------------------------------------------------------------------


class TestConfidenceOverlay:
    @pytest.mark.parametrize(
        ("confidence", "expected_label"),
        [
            (0.95, "HIGH"),
            (0.6, "MEDIUM"),
            (0.3, "LOW"),
        ],
    )
    def test_returns_valid_png(
        self, pdf_page: pymupdf.Page, confidence: float, expected_label: str
    ) -> None:
        resolved = ResolvedPageIR(
            page_number=1,
            doc_id="test",
            width_pt=612,
            height_pt=792,
            page_confidence=confidence,
            confidence_reasons=["test_reason"],
            render_mode="semantic",
        )
        result = render_confidence_overlay(pdf_page, resolved)
        assert result[:4] == _PNG_MAGIC
        assert len(result) > _MIN_SIZE
        # Label is baked into the PNG — we just verify the render completes
        _ = expected_label
