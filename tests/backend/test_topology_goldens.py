"""Golden tests for Architecture 3 intermediate topology/entity outputs.

Catches regressions in region segmentation, reading order, furniture
subtraction, and figure-caption linking by comparing curated hard-page
fixtures against checked-in expected outputs.

Each fixture is a synthetic PrimitivePageEvidence run through the pure-function
utilities (no PDF or network access required).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import orjson
import pytest

from aeon_reader_pipeline.models.evidence_models import (
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    PageReadingOrder,
    PageRegionGraph,
    PrimitivePageEvidence,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.furniture_detection import detect_furniture
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions
from aeon_reader_pipeline.utils.reading_order import compute_reading_order
from tests.backend.builders import (
    drawing as _drawing,
)
from tests.backend.builders import (
    empty_furniture as _empty_furniture,
)
from tests.backend.builders import (
    image as _image,
)
from tests.backend.builders import (
    page as _page_builder,
)
from tests.backend.builders import (
    table as _table,
)
from tests.backend.builders import (
    text as _text,
)

GOLDENS_DIR = Path(__file__).parent / "goldens" / "topology"

# Set to True to regenerate golden files (run once, then set back to False)
_REGENERATE = False


# ---------------------------------------------------------------------------
# Golden file helpers
# ---------------------------------------------------------------------------


def _golden_path(fixture_name: str, artifact_name: str) -> Path:
    return GOLDENS_DIR / fixture_name / f"{artifact_name}.json"


def _serialize(model: PageRegionGraph | PageReadingOrder) -> dict[str, Any]:
    """Serialize a model to a comparable dict, stripping run-specific fields."""
    data: dict[str, Any] = json.loads(
        orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    )
    data.pop("doc_id", None)
    data.pop("detection_version", None)
    return data


def _save_golden(fixture_name: str, artifact_name: str, data: dict[str, Any]) -> None:
    path = _golden_path(fixture_name, artifact_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n")


def _load_golden(fixture_name: str, artifact_name: str) -> dict[str, Any] | None:
    path = _golden_path(fixture_name, artifact_name)
    if not path.exists():
        return None
    return json.loads(path.read_bytes())


def _compare_golden(
    fixture_name: str,
    artifact_name: str,
    model: PageRegionGraph | PageReadingOrder,
) -> None:
    actual = _serialize(model)
    golden = _load_golden(fixture_name, artifact_name)

    if golden is None or _REGENERATE:
        _save_golden(fixture_name, artifact_name, actual)
        if golden is None:
            pytest.skip(f"Golden generated for {fixture_name}/{artifact_name} — rerun")
        golden = actual

    _assert_topology_equal(actual, golden, f"{fixture_name}/{artifact_name}")


def _assert_topology_equal(
    actual: dict[str, Any],
    golden: dict[str, Any],
    label: str,
) -> None:
    """Deep structural comparison for topology artifacts."""
    assert actual["page_number"] == golden["page_number"], f"{label}: page_number mismatch"

    if "regions" in actual:
        assert actual.get("width_pt") == pytest.approx(golden.get("width_pt"), abs=0.1), (
            f"{label}: width_pt mismatch"
        )
        assert actual.get("height_pt") == pytest.approx(golden.get("height_pt"), abs=0.1), (
            f"{label}: height_pt mismatch"
        )
        assert actual.get("furniture_ids_excluded") == golden.get("furniture_ids_excluded"), (
            f"{label}: furniture_ids_excluded mismatch"
        )
        _assert_regions_equal(actual, golden, label)
    if "entries" in actual:
        assert actual.get("total_regions") == golden.get("total_regions"), (
            f"{label}: total_regions mismatch"
        )
        _assert_reading_order_equal(actual, golden, label)


def _assert_regions_equal(
    actual: dict[str, Any],
    golden: dict[str, Any],
    label: str,
) -> None:
    actual_regions = actual["regions"]
    golden_regions = golden["regions"]
    assert len(actual_regions) == len(golden_regions), (
        f"{label}: region count {len(actual_regions)} != {len(golden_regions)}"
    )

    for i, (ar, gr) in enumerate(zip(actual_regions, golden_regions, strict=True)):
        prefix = f"{label} region[{i}]"
        assert ar["kind_hint"] == gr["kind_hint"], f"{prefix}: kind_hint mismatch"
        assert ar["band_index"] == gr["band_index"], f"{prefix}: band_index mismatch"
        assert ar.get("column_index") == gr.get("column_index"), f"{prefix}: column_index mismatch"
        assert ar.get("parent_region_id") == gr.get("parent_region_id"), (
            f"{prefix}: parent_region_id mismatch"
        )
        # Source evidence IDs (which primitives contribute to this region)
        assert sorted(ar.get("source_evidence_ids", [])) == sorted(
            gr.get("source_evidence_ids", [])
        ), f"{prefix}: source_evidence_ids mismatch"
        # Bbox comparison with tolerance
        _assert_bbox_approx(ar["bbox"], gr["bbox"], prefix)
        # Confidence value
        assert ar["confidence"]["value"] == pytest.approx(gr["confidence"]["value"], abs=0.01), (
            f"{prefix}: confidence mismatch"
        )

    # Edge comparison
    actual_edges = actual["edges"]
    golden_edges = golden["edges"]
    assert len(actual_edges) == len(golden_edges), (
        f"{label}: edge count {len(actual_edges)} != {len(golden_edges)}"
    )
    for i, (ae, ge) in enumerate(zip(actual_edges, golden_edges, strict=True)):
        prefix = f"{label} edge[{i}]"
        assert ae["edge_type"] == ge["edge_type"], f"{prefix}: edge_type mismatch"
        assert ae["src_region_id"] == ge["src_region_id"], f"{prefix}: src mismatch"
        assert ae["dst_region_id"] == ge["dst_region_id"], f"{prefix}: dst mismatch"


def _assert_reading_order_equal(
    actual: dict[str, Any],
    golden: dict[str, Any],
    label: str,
) -> None:
    actual_entries = actual["entries"]
    golden_entries = golden["entries"]
    assert len(actual_entries) == len(golden_entries), (
        f"{label}: entry count {len(actual_entries)} != {len(golden_entries)}"
    )

    for i, (ae, ge) in enumerate(zip(actual_entries, golden_entries, strict=True)):
        prefix = f"{label} entry[{i}]"
        assert ae["sequence_index"] == ge["sequence_index"], f"{prefix}: sequence_index mismatch"
        assert ae["region_id"] == ge["region_id"], f"{prefix}: region_id mismatch"
        assert ae["kind_hint"] == ge["kind_hint"], f"{prefix}: kind_hint mismatch"
        assert ae["flow_role"] == ge["flow_role"], f"{prefix}: flow_role mismatch"

    assert actual.get("unassigned_region_ids") == golden.get("unassigned_region_ids"), (
        f"{label}: unassigned_region_ids mismatch"
    )


def _assert_bbox_approx(
    actual: dict[str, float],
    golden: dict[str, float],
    prefix: str,
) -> None:
    for key in ("x0", "y0", "x1", "y1"):
        assert actual[key] == pytest.approx(golden[key], abs=0.001), (
            f"{prefix}: bbox.{key} mismatch"
        )


# ---------------------------------------------------------------------------
# Primitive builders (delegated to tests.backend.builders)
# ---------------------------------------------------------------------------


def _page(
    page_number: int,
    *,
    text: list[TextPrimitiveEvidence] | None = None,
    images: list[ImagePrimitiveEvidence] | None = None,
    tables: list[TablePrimitiveEvidence] | None = None,
    drawings: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    """Thin wrapper preserving the original ``text=`` kwarg name."""
    return _page_builder(
        page_number,
        text_prims=text,
        images=images,
        tables=tables,
        drawings=drawings,
    )


# ---------------------------------------------------------------------------
# Fixture: two-column page with full-width interruption
# ---------------------------------------------------------------------------
# Layout:
#   Band 0: full-width title (single column)
#   Band 1: two-column body text (left + right)
#   Band 2: full-width interruption note
#   Band 3: two-column body text continued
# ---------------------------------------------------------------------------


def _build_two_column_interruption() -> PrimitivePageEvidence:
    return _page(
        1,
        text=[
            # Band 0: full-width title at top
            _text(0, 1, 0.05, 0.03, 0.95, 0.07, "Chapter Title"),
            # Band 1: two-column body (left column)
            _text(1, 1, 0.05, 0.12, 0.46, 0.16, "Left column paragraph one."),
            _text(2, 1, 0.05, 0.17, 0.46, 0.21, "Left column paragraph two."),
            # Band 1: two-column body (right column)
            _text(3, 1, 0.54, 0.12, 0.95, 0.16, "Right column paragraph one."),
            _text(4, 1, 0.54, 0.17, 0.95, 0.21, "Right column paragraph two."),
            # Band 2: full-width interruption (note/callout)
            _text(5, 1, 0.05, 0.27, 0.95, 0.31, "Important note that spans full width."),
            # Band 3: two-column body continued (left)
            _text(6, 1, 0.05, 0.37, 0.46, 0.41, "Left continued paragraph."),
            # Band 3: two-column body continued (right)
            _text(7, 1, 0.54, 0.37, 0.95, 0.41, "Right continued paragraph."),
        ],
    )


class TestTwoColumnInterruption:
    """Golden tests for a two-column page with a full-width interruption band."""

    FIXTURE = "two_column_interruption"

    def test_region_graph(self) -> None:
        prim = _build_two_column_interruption()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        _compare_golden(self.FIXTURE, "regions", graph)

        # Structural assertions (must hold even after golden regeneration)
        bands = [r for r in graph.regions if r.kind_hint == "band"]
        columns = [r for r in graph.regions if r.kind_hint == "column"]
        assert len(bands) == 4, "Expected 4 bands (title, body, interruption, body)"
        assert len(columns) == 4, "Expected 4 columns (2 per multi-col band)"

        # Bands 1 and 3 should have 2 columns each
        for b in bands:
            if b.band_index in (1, 3):
                assert b.features.get("column_count") == 2

    def test_reading_order(self) -> None:
        prim = _build_two_column_interruption()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        order = compute_reading_order(graph)
        _compare_golden(self.FIXTURE, "reading_order", order)

        # Band 2 (interruption) should have flow_role="interruption"
        interruptions = [e for e in order.entries if e.flow_role == "interruption"]
        assert len(interruptions) == 1, "Expected exactly one interruption"

        # First entry should be title band (main), then columns
        assert order.entries[0].kind_hint == "band"
        assert order.entries[0].flow_role == "main"

        # No unassigned regions
        assert order.unassigned_region_ids == []


# ---------------------------------------------------------------------------
# Fixture: page with callout box and sidebar
# ---------------------------------------------------------------------------
# Layout:
#   Band 0: full-width heading
#   Band 1: narrow sidebar (left) + main body (right)
#   Band 2: full-width text with a drawing-enclosed callout box
# ---------------------------------------------------------------------------


def _build_callout_sidebar() -> PrimitivePageEvidence:
    return _page(
        2,
        text=[
            # Band 0: heading
            _text(0, 2, 0.05, 0.03, 0.95, 0.07, "Section Heading"),
            # Band 1: sidebar (narrow left) + main body (wide right)
            _text(1, 2, 0.05, 0.12, 0.22, 0.16, "Sidebar note"),
            _text(2, 2, 0.05, 0.17, 0.22, 0.21, "Sidebar extra"),
            _text(3, 2, 0.30, 0.12, 0.95, 0.16, "Main body paragraph one."),
            _text(4, 2, 0.30, 0.17, 0.95, 0.21, "Main body paragraph two."),
            # Band 2: full-width text + callout box
            _text(5, 2, 0.05, 0.28, 0.95, 0.32, "Normal text before callout."),
            # Text inside the callout drawing
            _text(6, 2, 0.12, 0.35, 0.88, 0.39, "Warning: this is important!"),
            _text(7, 2, 0.12, 0.40, 0.88, 0.44, "Please read carefully."),
            _text(8, 2, 0.12, 0.45, 0.88, 0.49, "Third line of callout."),
        ],
        drawings=[
            # Callout box enclosing texts 6, 7, 8
            _drawing(0, 2, 0.10, 0.34, 0.90, 0.50),
        ],
    )


class TestCalloutSidebar:
    """Golden tests for a page with a sidebar column and a callout box."""

    FIXTURE = "callout_sidebar"

    def test_region_graph(self) -> None:
        prim = _build_callout_sidebar()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        _compare_golden(self.FIXTURE, "regions", graph)

        # Verify sidebar detection
        sidebars = [r for r in graph.regions if r.kind_hint == "sidebar"]
        assert len(sidebars) >= 1, "Expected at least one sidebar region"

        # Verify callout detection
        callouts = [r for r in graph.regions if r.kind_hint == "callout"]
        assert len(callouts) >= 1, "Expected at least one callout region"
        assert callouts[0].confidence.value >= 0.6

    def test_reading_order(self) -> None:
        prim = _build_callout_sidebar()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        order = compute_reading_order(graph)
        _compare_golden(self.FIXTURE, "reading_order", order)

        # Sidebar and callout should be tagged as aside
        asides = [e for e in order.entries if e.flow_role == "aside"]
        aside_kinds = {e.kind_hint for e in asides}
        assert "sidebar" in aside_kinds, "Sidebar should have flow_role=aside"
        assert "callout" in aside_kinds, "Callout should have flow_role=aside"

        assert order.unassigned_region_ids == []


# ---------------------------------------------------------------------------
# Fixture: page with multiple figures and captions
# ---------------------------------------------------------------------------
# Layout:
#   Band 0: heading
#   Band 1: text + figure A (left area)
#   Band 2: figure B (large) + text below with caption
#   Band 3: table with structured data
# ---------------------------------------------------------------------------


def _build_figure_caption_table() -> PrimitivePageEvidence:
    return _page(
        3,
        text=[
            # Band 0: heading
            _text(0, 3, 0.05, 0.02, 0.95, 0.06, "Results Overview"),
            # Band 1: body text alongside figure
            _text(1, 3, 0.05, 0.10, 0.45, 0.14, "As shown in Figure 1..."),
            _text(2, 3, 0.05, 0.15, 0.45, 0.19, "The data demonstrates..."),
            # Band 2: caption text below large figure
            _text(3, 3, 0.15, 0.48, 0.85, 0.52, "Figure 2: Experimental setup diagram."),
            _text(4, 3, 0.05, 0.55, 0.95, 0.59, "Below the figure, analysis continues."),
            # Band 3: no text near table (table stands alone)
        ],
        images=[
            # Figure A: small image in band 1 (right side)
            _image(0, 3, 0.50, 0.09, 0.90, 0.22, content_hash="fig_a_hash"),
            # Figure B: large image in band 2
            _image(1, 3, 0.10, 0.26, 0.90, 0.46, content_hash="fig_b_hash"),
        ],
        tables=[
            # Data table in band 3
            _table(0, 3, 0.10, 0.65, 0.90, 0.85, rows=4, cols=3, strategy="lines_strict"),
        ],
    )


class TestFigureCaptionTable:
    """Golden tests for a page with figures, a caption, and a table."""

    FIXTURE = "figure_caption_table"

    def test_region_graph(self) -> None:
        prim = _build_figure_caption_table()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        _compare_golden(self.FIXTURE, "regions", graph)

        # Verify figure regions detected
        figures = [r for r in graph.regions if r.kind_hint == "figure"]
        assert len(figures) == 2, "Expected 2 figure regions"

        # Verify table region detected with high confidence
        tables = [r for r in graph.regions if r.kind_hint == "table"]
        assert len(tables) == 1, "Expected 1 table region"
        assert tables[0].confidence.value >= 0.9, (
            "lines_strict 4x3 table should have high confidence"
        )

    def test_reading_order(self) -> None:
        prim = _build_figure_caption_table()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        order = compute_reading_order(graph)
        _compare_golden(self.FIXTURE, "reading_order", order)

        # Figures and tables should appear in reading order
        kinds_in_order = [e.kind_hint for e in order.entries]
        assert "figure" in kinds_in_order, "Figures should be in reading order"
        assert "table" in kinds_in_order, "Table should be in reading order"
        assert order.unassigned_region_ids == []


# ---------------------------------------------------------------------------
# Fixture: page with repeated furniture that must be subtracted
# ---------------------------------------------------------------------------
# We simulate a multi-page document where headers/footers repeat, then
# verify that the content page's region graph excludes furniture zones.
# ---------------------------------------------------------------------------


def _build_furniture_pages() -> list[PrimitivePageEvidence]:
    """Build 4 pages with repeated header/footer furniture."""
    pages: list[PrimitivePageEvidence] = []
    for pn in range(1, 5):
        texts = [
            # Repeated header (same text, same position on every page)
            _text(0, pn, 0.05, 0.01, 0.95, 0.04, "Aeon Trespass: Odyssey — Core Rulebook"),
            # Repeated footer / page number
            _text(1, pn, 0.45, 0.96, 0.55, 0.99, str(pn)),
            # Unique body content per page
            _text(2, pn, 0.05, 0.10, 0.95, 0.14, f"Page {pn} body paragraph one."),
            _text(3, pn, 0.05, 0.16, 0.95, 0.20, f"Page {pn} body paragraph two."),
            _text(4, pn, 0.05, 0.22, 0.95, 0.26, f"Page {pn} body paragraph three."),
        ]
        pages.append(_page(pn, text=texts))
    return pages


class TestFurnitureSubtraction:
    """Golden tests for furniture detection and subtraction."""

    FIXTURE = "furniture_subtraction"

    def test_furniture_detection(self) -> None:
        """Repeated header/footer should be detected as furniture."""
        pages = _build_furniture_pages()
        profile = detect_furniture(pages)

        # Should find at least header and page number as furniture
        assert len(profile.furniture_candidates) >= 2, (
            "Expected at least 2 furniture candidates (header + page number)"
        )
        types = {c.furniture_type for c in profile.furniture_candidates}
        assert "header" in types, "Header furniture should be detected"
        assert "page_number" in types or "footer" in types, (
            "Page number or footer furniture should be detected"
        )

    def test_region_graph_excludes_furniture(self) -> None:
        """Region graph for page 2 should not contain furniture primitives."""
        pages = _build_furniture_pages()
        profile = detect_furniture(pages)

        # Get furniture IDs for page 2
        furn_ids = [c.candidate_id for c in profile.furniture_candidates if 2 in c.page_numbers]
        assert len(furn_ids) >= 2, "Page 2 should have furniture candidates"

        graph = segment_page_regions(pages[1], profile, furn_ids)
        _compare_golden(self.FIXTURE, "regions_p2", graph)

        # Body content should form regions, but header/footer should be excluded
        all_source_ids: list[str] = []
        for region in graph.regions:
            all_source_ids.extend(region.source_evidence_ids)

        # Header primitive (text:p0002:000) should NOT be in any region
        assert "text:p0002:000" not in all_source_ids, "Header text should be excluded from regions"
        # Footer primitive (text:p0002:001) should NOT be in any region
        assert "text:p0002:001" not in all_source_ids, (
            "Footer/page-number text should be excluded from regions"
        )
        # Body text should be present
        assert "text:p0002:002" in all_source_ids, "Body text should be in regions"

    def test_reading_order_excludes_furniture(self) -> None:
        """Reading order should only contain body content regions."""
        pages = _build_furniture_pages()
        profile = detect_furniture(pages)
        furn_ids = [c.candidate_id for c in profile.furniture_candidates if 2 in c.page_numbers]

        graph = segment_page_regions(pages[1], profile, furn_ids)
        order = compute_reading_order(graph)
        _compare_golden(self.FIXTURE, "reading_order_p2", order)

        # All entries should be main flow (no interruptions in single-col body)
        for entry in order.entries:
            assert entry.flow_role == "main"
        assert order.unassigned_region_ids == []


# ---------------------------------------------------------------------------
# Cross-fixture consistency check
# ---------------------------------------------------------------------------


class TestTopologyInvariants:
    """Invariants that must hold for any topology output."""

    @pytest.mark.parametrize(
        "builder",
        [
            _build_two_column_interruption,
            _build_callout_sidebar,
            _build_figure_caption_table,
        ],
        ids=["two_col", "callout", "figure_table"],
    )
    def test_region_ids_unique(self, builder: Any) -> None:
        prim = builder()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        ids = [r.region_id for r in graph.regions]
        assert len(ids) == len(set(ids)), "Region IDs must be unique"

    @pytest.mark.parametrize(
        "builder",
        [
            _build_two_column_interruption,
            _build_callout_sidebar,
            _build_figure_caption_table,
        ],
        ids=["two_col", "callout", "figure_table"],
    )
    def test_containment_edges_reference_valid_regions(self, builder: Any) -> None:
        prim = builder()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        ids = {r.region_id for r in graph.regions}
        for edge in graph.edges:
            assert edge.src_region_id in ids, f"Edge src {edge.src_region_id} not in regions"
            assert edge.dst_region_id in ids, f"Edge dst {edge.dst_region_id} not in regions"

    @pytest.mark.parametrize(
        "builder",
        [
            _build_two_column_interruption,
            _build_callout_sidebar,
            _build_figure_caption_table,
        ],
        ids=["two_col", "callout", "figure_table"],
    )
    def test_reading_order_covers_all_content_regions(self, builder: Any) -> None:
        prim = builder()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        order = compute_reading_order(graph)

        # Every region should be either assigned or explicitly unassigned
        assigned = {e.region_id for e in order.entries}
        unassigned = set(order.unassigned_region_ids)
        all_ids = {r.region_id for r in graph.regions}
        # Bands with columns are structural — assigned implicitly
        covered = assigned | unassigned
        structural_bands = set()
        for edge in graph.edges:
            if edge.edge_type == "contains":
                structural_bands.add(edge.src_region_id)
        assert all_ids == covered | structural_bands, (
            f"Uncovered regions: {all_ids - covered - structural_bands}"
        )

    @pytest.mark.parametrize(
        "builder",
        [
            _build_two_column_interruption,
            _build_callout_sidebar,
            _build_figure_caption_table,
        ],
        ids=["two_col", "callout", "figure_table"],
    )
    def test_reading_order_sequence_is_contiguous(self, builder: Any) -> None:
        prim = builder()
        graph = segment_page_regions(prim, _empty_furniture(), [])
        order = compute_reading_order(graph)

        indices = [e.sequence_index for e in order.entries]
        assert indices == list(range(len(indices))), "Sequence indices must be contiguous 0..N-1"
