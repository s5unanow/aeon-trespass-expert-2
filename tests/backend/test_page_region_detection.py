"""Tests for page region segmentation."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    FurnitureCandidate,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PageRegionGraph,
    PrimitivePageEvidence,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _make_page(
    page_number: int = 1,
    *,
    doc_id: str = "test-doc",
    text_primitives: list[TextPrimitiveEvidence] | None = None,
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    table_primitives: list[TablePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id=doc_id,
        width_pt=612.0,
        height_pt=792.0,
        text_primitives=text_primitives or [],
        image_primitives=image_primitives or [],
        table_primitives=table_primitives or [],
        drawing_primitives=drawing_primitives or [],
    )


def _empty_furniture(doc_id: str = "test-doc") -> DocumentFurnitureProfile:
    return DocumentFurnitureProfile(doc_id=doc_id, total_pages_analyzed=1)


def _furniture_with_header(doc_id: str = "test-doc") -> DocumentFurnitureProfile:
    return DocumentFurnitureProfile(
        doc_id=doc_id,
        total_pages_analyzed=5,
        furniture_candidates=[
            FurnitureCandidate(
                candidate_id="furn:header:000",
                furniture_type="header",
                bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
                source_primitive_kind="text",
                page_numbers=[1, 2, 3, 4, 5],
                repetition_rate=1.0,
                confidence=1.0,
                text_sample="Rules Reference",
            ),
        ],
    )


class TestEmptyPage:
    def test_empty_page_returns_empty_graph(self) -> None:
        page = _make_page()
        graph = segment_page_regions(page, _empty_furniture(), [])
        assert isinstance(graph, PageRegionGraph)
        assert graph.page_number == 1
        assert graph.regions == []
        assert graph.edges == []

    def test_graph_preserves_page_metadata(self) -> None:
        page = _make_page(page_number=3, doc_id="my-doc")
        graph = segment_page_regions(page, _empty_furniture("my-doc"), [])
        assert graph.page_number == 3
        assert graph.doc_id == "my-doc"
        assert graph.width_pt == 612.0
        assert graph.height_pt == 792.0


class TestSingleBand:
    def test_single_text_primitive_creates_one_band(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.1, 0.9, 0.2),
                    text="Hello",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert len(bands) == 1
        assert "txt-0001" in bands[0].source_evidence_ids
        assert bands[0].band_index == 0

    def test_close_primitives_stay_in_same_band(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.15),
                    text="Line 1",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.1, 0.16, 0.9, 0.21),
                    text="Line 2",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert len(bands) == 1
        assert len(bands[0].source_evidence_ids) == 2


class TestMultipleBands:
    def test_vertical_gap_splits_into_two_bands(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.05, 0.9, 0.10),
                    text="Top text",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.1, 0.50, 0.9, 0.55),
                    text="Bottom text",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert len(bands) == 2
        assert bands[0].band_index == 0
        assert bands[1].band_index == 1

    def test_adjacency_edges_between_bands(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.05, 0.9, 0.10),
                    text="Top",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.1, 0.50, 0.9, 0.55),
                    text="Bottom",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        adj_edges = [e for e in graph.edges if e.edge_type == "adjacent_to"]
        assert len(adj_edges) == 1


class TestColumnDetection:
    def test_two_columns_detected(self) -> None:
        """Primitives separated by a horizontal gap form two columns."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.05, 0.10, 0.45, 0.15),
                    text="Left column text",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.05, 0.16, 0.45, 0.21),
                    text="Left column line 2",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0003",
                    bbox_norm=_bbox(0.55, 0.10, 0.95, 0.15),
                    text="Right column text",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0004",
                    bbox_norm=_bbox(0.55, 0.16, 0.95, 0.21),
                    text="Right column line 2",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        columns = [r for r in graph.regions if r.kind_hint == "column"]
        assert len(columns) == 2
        assert columns[0].column_index == 0
        assert columns[1].column_index == 1

        # Column 0 should have left primitives
        assert "txt-0001" in columns[0].source_evidence_ids
        assert "txt-0002" in columns[0].source_evidence_ids

        # Column 1 should have right primitives
        assert "txt-0003" in columns[1].source_evidence_ids
        assert "txt-0004" in columns[1].source_evidence_ids

    def test_columns_have_containment_edges(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.05, 0.10, 0.45, 0.20),
                    text="Left",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.55, 0.10, 0.95, 0.20),
                    text="Right",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        contain_edges = [e for e in graph.edges if e.edge_type == "contains"]
        assert len(contain_edges) == 2
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert len(bands) == 1
        for edge in contain_edges:
            assert edge.src_region_id == bands[0].region_id

    def test_no_gutter_means_single_column(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.15),
                    text="Full width text line 1",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.1, 0.16, 0.9, 0.21),
                    text="Full width text line 2",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        columns = [r for r in graph.regions if r.kind_hint == "column"]
        assert len(columns) == 0  # No column sub-regions for single-column
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert len(bands) == 1
        assert bands[0].features.get("column_count") == 1

    def test_column_count_in_band_features(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.05, 0.10, 0.45, 0.20),
                    text="Left",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.55, 0.10, 0.95, 0.20),
                    text="Right",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        assert bands[0].features["column_count"] == 2


class TestFurnitureExclusion:
    def test_furniture_primitives_excluded(self) -> None:
        """Primitives overlapping furniture are excluded from regions."""
        page = _make_page(
            text_primitives=[
                # This overlaps with furniture header
                TextPrimitiveEvidence(
                    primitive_id="txt-header",
                    bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
                    text="Rules Reference",
                ),
                # Body content
                TextPrimitiveEvidence(
                    primitive_id="txt-body",
                    bbox_norm=_bbox(0.1, 0.15, 0.9, 0.25),
                    text="Body text here.",
                ),
            ],
        )
        profile = _furniture_with_header()
        graph = segment_page_regions(page, profile, ["furn:header:000"])

        # Only body text should appear in regions
        all_ids = []
        for r in graph.regions:
            all_ids.extend(r.source_evidence_ids)
        assert "txt-body" in all_ids
        assert "txt-header" not in all_ids
        assert graph.furniture_ids_excluded == ["furn:header:000"]

    def test_no_furniture_ids_keeps_all_primitives(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
                    text="Header-looking text",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.1, 0.15, 0.9, 0.25),
                    text="Body text",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        all_ids: list[str] = []
        for r in graph.regions:
            all_ids.extend(r.source_evidence_ids)
        assert "txt-0001" in all_ids
        assert "txt-0002" in all_ids


class TestFigureRegions:
    def test_image_primitive_creates_figure_region(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.20),
                    text="Intro text",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img-0001",
                    bbox_norm=_bbox(0.2, 0.12, 0.8, 0.18),
                    content_hash="sha256:abc",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        figures = [r for r in graph.regions if r.kind_hint == "figure"]
        assert len(figures) == 1
        assert "img-0001" in figures[0].source_evidence_ids

    def test_figure_has_containment_edge(self) -> None:
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img-0001",
                    bbox_norm=_bbox(0.2, 0.30, 0.8, 0.60),
                    content_hash="sha256:abc",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        contain_edges = [e for e in graph.edges if e.edge_type == "contains"]
        assert len(contain_edges) == 1
        figures = [r for r in graph.regions if r.kind_hint == "figure"]
        assert contain_edges[0].dst_region_id == figures[0].region_id


class TestTableRegions:
    def test_table_primitive_creates_table_region(self) -> None:
        page = _make_page(
            table_primitives=[
                TablePrimitiveEvidence(
                    primitive_id="tbl-0001",
                    bbox_norm=_bbox(0.1, 0.30, 0.9, 0.60),
                    rows=3,
                    cols=4,
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        tables = [r for r in graph.regions if r.kind_hint == "table"]
        assert len(tables) == 1
        assert "tbl-0001" in tables[0].source_evidence_ids


class TestFurnitureImageExclusion:
    def test_furniture_image_produces_no_figure_region(self) -> None:
        """An image at a furniture position is excluded from figure regions."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.15, 0.9, 0.25),
                    text="Body text",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img-logo",
                    bbox_norm=_bbox(0.0, 0.01, 0.15, 0.05),
                    content_hash="sha256:logo",
                ),
            ],
        )
        profile = DocumentFurnitureProfile(
            doc_id="test-doc",
            total_pages_analyzed=5,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="furn:ornament:000",
                    furniture_type="ornament",
                    bbox_norm=_bbox(0.0, 0.01, 0.15, 0.05),
                    source_primitive_kind="image",
                    page_numbers=[1, 2, 3, 4, 5],
                    repetition_rate=1.0,
                    content_hash="sha256:logo",
                ),
            ],
        )
        graph = segment_page_regions(page, profile, ["furn:ornament:000"])
        figures = [r for r in graph.regions if r.kind_hint == "figure"]
        assert len(figures) == 0

    def test_content_image_still_creates_figure_region(self) -> None:
        """A non-furniture image still produces a figure region."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.20),
                    text="Body text",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img-content",
                    bbox_norm=_bbox(0.2, 0.30, 0.8, 0.60),
                    content_hash="sha256:content",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        figures = [r for r in graph.regions if r.kind_hint == "figure"]
        assert len(figures) == 1
        assert "img-content" in figures[0].source_evidence_ids


class TestDecorativeDrawingExclusion:
    def test_decorative_drawings_excluded(self) -> None:
        """Decorative drawings are not included in region primitives."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.20),
                    text="Content",
                ),
            ],
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drw-0001",
                    bbox_norm=_bbox(0.0, 0.0, 1.0, 1.0),
                    path_count=20,
                    is_decorative=True,
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        all_ids: list[str] = []
        for r in graph.regions:
            all_ids.extend(r.source_evidence_ids)
        assert "drw-0001" not in all_ids
        assert "txt-0001" in all_ids


class TestRegionGraphRoundTrip:
    def test_json_roundtrip(self) -> None:
        """PageRegionGraph survives JSON serialization round-trip."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.05, 0.10, 0.45, 0.20),
                    text="Left",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.55, 0.10, 0.95, 0.20),
                    text="Right",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        payload = graph.model_dump(mode="json")
        restored = PageRegionGraph.model_validate(payload)
        assert restored == graph


class TestRegionIdsUnique:
    def test_all_region_ids_unique(self) -> None:
        """All region IDs in a graph are unique."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt-0001",
                    bbox_norm=_bbox(0.05, 0.05, 0.45, 0.10),
                    text="Top left",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0002",
                    bbox_norm=_bbox(0.55, 0.05, 0.95, 0.10),
                    text="Top right",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt-0003",
                    bbox_norm=_bbox(0.1, 0.50, 0.9, 0.55),
                    text="Bottom full-width",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img-0001",
                    bbox_norm=_bbox(0.2, 0.07, 0.4, 0.09),
                    content_hash="sha256:abc",
                ),
            ],
        )
        graph = segment_page_regions(page, _empty_furniture(), [])
        ids = [r.region_id for r in graph.regions]
        assert len(ids) == len(set(ids))
