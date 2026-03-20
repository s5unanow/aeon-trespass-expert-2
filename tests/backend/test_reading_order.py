"""Tests for reading-order reconstruction from PageRegionGraph."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    NormalizedBBox,
    PageReadingOrder,
    PageRegionGraph,
    ReadingOrderEntry,
    RegionCandidate,
    RegionConfidence,
    RegionEdge,
)
from aeon_reader_pipeline.utils.reading_order import compute_reading_order


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _band(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    column_count: int = 1,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="band",
        bbox=bbox,
        band_index=band_index,
        features={"column_count": column_count},
        confidence=RegionConfidence(value=0.9, reasons=["horizontal_partition"]),
    )


def _column(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    column_index: int,
    parent_id: str,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="column",
        bbox=bbox,
        parent_region_id=parent_id,
        band_index=band_index,
        column_index=column_index,
        confidence=RegionConfidence(value=0.85, reasons=["gutter_detected"]),
    )


def _figure(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    parent_id: str,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="figure",
        bbox=bbox,
        parent_region_id=parent_id,
        band_index=band_index,
        confidence=RegionConfidence(value=0.8, reasons=["image_primitive"]),
    )


def _table(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    parent_id: str,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="table",
        bbox=bbox,
        parent_region_id=parent_id,
        band_index=band_index,
        confidence=RegionConfidence(value=0.8, reasons=["table_primitive"]),
    )


def _sidebar(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    parent_id: str,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="sidebar",
        bbox=bbox,
        parent_region_id=parent_id,
        band_index=band_index,
        confidence=RegionConfidence(value=0.7, reasons=["narrow_width"]),
    )


def _callout(
    region_id: str,
    bbox: NormalizedBBox,
    band_index: int,
    parent_id: str,
) -> RegionCandidate:
    return RegionCandidate(
        region_id=region_id,
        kind_hint="callout",
        bbox=bbox,
        parent_region_id=parent_id,
        band_index=band_index,
        confidence=RegionConfidence(value=0.7, reasons=["bordered_box"]),
    )


def _graph(
    regions: list[RegionCandidate],
    edges: list[RegionEdge] | None = None,
    page_number: int = 1,
) -> PageRegionGraph:
    return PageRegionGraph(
        page_number=page_number,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        regions=regions,
        edges=edges or [],
    )


def _contains(src: str, dst: str) -> RegionEdge:
    return RegionEdge(edge_type="contains", src_region_id=src, dst_region_id=dst)


def _adjacent(src: str, dst: str) -> RegionEdge:
    return RegionEdge(edge_type="adjacent_to", src_region_id=src, dst_region_id=dst)


class TestEmptyGraph:
    def test_empty_graph_returns_empty_order(self) -> None:
        graph = _graph([])
        order = compute_reading_order(graph)
        assert isinstance(order, PageReadingOrder)
        assert order.page_number == 1
        assert order.entries == []
        assert order.total_regions == 0
        assert order.unassigned_region_ids == []


class TestSingleBand:
    def test_single_band_produces_one_entry(self) -> None:
        b = _band("reg:1:0", _bbox(0.1, 0.1, 0.9, 0.3), band_index=0)
        graph = _graph([b])
        order = compute_reading_order(graph)
        assert len(order.entries) == 1
        assert order.entries[0].region_id == "reg:1:0"
        assert order.entries[0].sequence_index == 0
        assert order.entries[0].flow_role == "main"
        assert order.entries[0].kind_hint == "band"

    def test_single_band_no_unassigned(self) -> None:
        b = _band("reg:1:0", _bbox(0.1, 0.1, 0.9, 0.3), band_index=0)
        graph = _graph([b])
        order = compute_reading_order(graph)
        assert order.unassigned_region_ids == []
        assert order.total_regions == 1


class TestMultipleBands:
    def test_bands_ordered_top_to_bottom(self) -> None:
        b0 = _band("reg:1:0", _bbox(0.1, 0.05, 0.9, 0.10), band_index=0)
        b1 = _band("reg:1:1", _bbox(0.1, 0.50, 0.9, 0.55), band_index=1)
        graph = _graph([b1, b0], [_adjacent("reg:1:0", "reg:1:1")])
        order = compute_reading_order(graph)
        assert len(order.entries) == 2
        assert order.entries[0].region_id == "reg:1:0"
        assert order.entries[1].region_id == "reg:1:1"
        assert order.entries[0].sequence_index == 0
        assert order.entries[1].sequence_index == 1

    def test_three_bands(self) -> None:
        b0 = _band("reg:1:0", _bbox(0.1, 0.05, 0.9, 0.15), band_index=0)
        b1 = _band("reg:1:1", _bbox(0.1, 0.30, 0.9, 0.45), band_index=1)
        b2 = _band("reg:1:2", _bbox(0.1, 0.60, 0.9, 0.75), band_index=2)
        graph = _graph(
            [b2, b0, b1],
            [_adjacent("reg:1:0", "reg:1:1"), _adjacent("reg:1:1", "reg:1:2")],
        )
        order = compute_reading_order(graph)
        ids = [e.region_id for e in order.entries]
        assert ids == ["reg:1:0", "reg:1:1", "reg:1:2"]


class TestTwoColumns:
    def test_columns_left_to_right(self) -> None:
        bb = _bbox(0.05, 0.10, 0.95, 0.80)
        b = _band("b0", bb, band_index=0, column_count=2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.10, 0.45, 0.80),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.55, 0.10, 0.95, 0.80),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )
        graph = _graph(
            [b, c1, c0],  # intentionally reversed
            [_contains("b0", "c0"), _contains("b0", "c1")],
        )
        order = compute_reading_order(graph)
        assert len(order.entries) == 2
        assert order.entries[0].region_id == "c0"  # left
        assert order.entries[1].region_id == "c1"  # right
        assert order.entries[0].column_index == 0
        assert order.entries[1].column_index == 1
        # Band itself is structural, not a content entry
        assert "b0" not in [e.region_id for e in order.entries]
        # But band is still assigned (not in unassigned)
        assert "b0" not in order.unassigned_region_ids

    def test_columns_flow_role_is_main(self) -> None:
        bb = _bbox(0.05, 0.10, 0.95, 0.80)
        b = _band("b0", bb, band_index=0, column_count=2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.10, 0.45, 0.80),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.55, 0.10, 0.95, 0.80),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )
        graph = _graph(
            [b, c0, c1],
            [_contains("b0", "c0"), _contains("b0", "c1")],
        )
        order = compute_reading_order(graph)
        for entry in order.entries:
            assert entry.flow_role == "main"


class TestFullWidthInterruption:
    """A 1-column band between two 2-column bands is an interruption."""

    def test_interruption_tagged(self) -> None:
        # Band 0: two columns
        b0 = _band("b0", _bbox(0.05, 0.05, 0.95, 0.30), 0, 2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.05, 0.45, 0.30),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.55, 0.05, 0.95, 0.30),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )
        # Band 1: full-width heading (interruption)
        b1 = _band("b1", _bbox(0.05, 0.35, 0.95, 0.40), 1, 1)
        # Band 2: two columns again
        b2 = _band("b2", _bbox(0.05, 0.45, 0.95, 0.80), 2, 2)
        c2 = _column(
            "c2",
            _bbox(0.05, 0.45, 0.45, 0.80),
            band_index=2,
            column_index=0,
            parent_id="b2",
        )
        c3 = _column(
            "c3",
            _bbox(0.55, 0.45, 0.95, 0.80),
            band_index=2,
            column_index=1,
            parent_id="b2",
        )

        graph = _graph(
            [b0, c0, c1, b1, b2, c2, c3],
            [
                _contains("b0", "c0"),
                _contains("b0", "c1"),
                _adjacent("b0", "b1"),
                _adjacent("b1", "b2"),
                _contains("b2", "c2"),
                _contains("b2", "c3"),
            ],
        )
        order = compute_reading_order(graph)

        ids = [e.region_id for e in order.entries]
        assert ids == ["c0", "c1", "b1", "c2", "c3"]

        # b1 is the interruption
        b1_entry = next(e for e in order.entries if e.region_id == "b1")
        assert b1_entry.flow_role == "interruption"

        # Columns are main flow
        for eid in ["c0", "c1", "c2", "c3"]:
            entry = next(e for e in order.entries if e.region_id == eid)
            assert entry.flow_role == "main"

    def test_all_single_column_no_interruption(self) -> None:
        """When all bands are single-column, none are tagged as interruption."""
        b0 = _band("b0", _bbox(0.1, 0.05, 0.9, 0.30), band_index=0)
        b1 = _band("b1", _bbox(0.1, 0.40, 0.9, 0.60), band_index=1)
        graph = _graph([b0, b1], [_adjacent("b0", "b1")])
        order = compute_reading_order(graph)
        for entry in order.entries:
            assert entry.flow_role == "main"


class TestFiguresAndTables:
    def test_figure_emitted_after_columns(self) -> None:
        b = _band("b0", _bbox(0.05, 0.10, 0.95, 0.80), 0, 2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.10, 0.45, 0.80),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.55, 0.10, 0.95, 0.80),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )
        fig = _figure(
            "fig0",
            _bbox(0.20, 0.30, 0.40, 0.50),
            band_index=0,
            parent_id="b0",
        )

        graph = _graph(
            [b, c0, c1, fig],
            [_contains("b0", "c0"), _contains("b0", "c1"), _contains("b0", "fig0")],
        )
        order = compute_reading_order(graph)
        ids = [e.region_id for e in order.entries]
        assert ids == ["c0", "c1", "fig0"]
        fig_entry = next(e for e in order.entries if e.region_id == "fig0")
        assert fig_entry.kind_hint == "figure"
        assert fig_entry.flow_role == "main"

    def test_table_in_single_column_band(self) -> None:
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.60), band_index=0)
        tbl = _table("tbl0", _bbox(0.1, 0.20, 0.9, 0.50), band_index=0, parent_id="b0")
        graph = _graph(
            [b, tbl],
            [_contains("b0", "tbl0")],
        )
        order = compute_reading_order(graph)
        ids = [e.region_id for e in order.entries]
        assert ids == ["b0", "tbl0"]

    def test_multiple_inline_sorted_by_y(self) -> None:
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.80), band_index=0)
        fig_low = _figure("fig_low", _bbox(0.2, 0.60, 0.8, 0.75), band_index=0, parent_id="b0")
        fig_high = _figure("fig_high", _bbox(0.2, 0.15, 0.8, 0.30), band_index=0, parent_id="b0")
        graph = _graph(
            [b, fig_low, fig_high],
            [_contains("b0", "fig_low"), _contains("b0", "fig_high")],
        )
        order = compute_reading_order(graph)
        ids = [e.region_id for e in order.entries]
        # Band first, then figures sorted by y0
        assert ids == ["b0", "fig_high", "fig_low"]


class TestSidebarsAndCallouts:
    def test_sidebar_tagged_as_aside(self) -> None:
        b = _band("b0", _bbox(0.05, 0.10, 0.95, 0.80), 0, 2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.10, 0.45, 0.80),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.55, 0.10, 0.95, 0.80),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )
        sb = _sidebar(
            "sb0",
            _bbox(0.80, 0.20, 0.95, 0.50),
            band_index=0,
            parent_id="b0",
        )

        graph = _graph(
            [b, c0, c1, sb],
            [
                _contains("b0", "c0"),
                _contains("b0", "c1"),
                _contains("b0", "sb0"),
            ],
        )
        order = compute_reading_order(graph)
        sb_entry = next(e for e in order.entries if e.region_id == "sb0")
        assert sb_entry.flow_role == "aside"
        assert sb_entry.kind_hint == "sidebar"
        assert "aside_placement" in sb_entry.confidence.reasons

    def test_callout_tagged_as_aside(self) -> None:
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.60), band_index=0)
        co = _callout("co0", _bbox(0.15, 0.20, 0.85, 0.40), band_index=0, parent_id="b0")
        graph = _graph(
            [b, co],
            [_contains("b0", "co0")],
        )
        order = compute_reading_order(graph)
        co_entry = next(e for e in order.entries if e.region_id == "co0")
        assert co_entry.flow_role == "aside"
        assert co_entry.kind_hint == "callout"

    def test_aside_comes_after_main_content(self) -> None:
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.60), band_index=0)
        sb = _sidebar("sb0", _bbox(0.75, 0.15, 0.89, 0.50), band_index=0, parent_id="b0")
        graph = _graph([b, sb], [_contains("b0", "sb0")])
        order = compute_reading_order(graph)
        ids = [e.region_id for e in order.entries]
        # Band (main content) emitted before sidebar (aside)
        assert ids == ["b0", "sb0"]


class TestSequenceIndices:
    def test_indices_are_contiguous(self) -> None:
        b0 = _band("b0", _bbox(0.1, 0.05, 0.9, 0.15), band_index=0)
        b1 = _band("b1", _bbox(0.1, 0.30, 0.9, 0.45), band_index=1)
        b2 = _band("b2", _bbox(0.1, 0.60, 0.9, 0.75), band_index=2)
        graph = _graph([b0, b1, b2])
        order = compute_reading_order(graph)
        indices = [e.sequence_index for e in order.entries]
        assert indices == [0, 1, 2]


class TestUnassignedRegions:
    def test_orphan_region_reported(self) -> None:
        """A region not in any band and not a band itself is unassigned."""
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.30), band_index=0)
        orphan = RegionCandidate(
            region_id="orphan",
            kind_hint="unknown",
            bbox=_bbox(0.0, 0.90, 0.1, 0.95),
        )
        graph = _graph([b, orphan])
        order = compute_reading_order(graph)
        assert "orphan" in order.unassigned_region_ids


class TestJsonRoundTrip:
    def test_reading_order_roundtrip(self) -> None:
        b = _band("b0", _bbox(0.1, 0.10, 0.9, 0.30), band_index=0)
        graph = _graph([b])
        order = compute_reading_order(graph)
        data = order.model_dump(mode="json")
        restored = PageReadingOrder.model_validate(data)
        assert restored == order

    def test_entry_roundtrip(self) -> None:
        entry = ReadingOrderEntry(
            sequence_index=0,
            region_id="reg:1:0",
            kind_hint="column",
            flow_role="main",
            band_index=0,
            column_index=1,
            confidence=RegionConfidence(value=0.85, reasons=["gutter_detected"]),
        )
        data = entry.model_dump(mode="json")
        restored = ReadingOrderEntry.model_validate(data)
        assert restored == entry


class TestComplexPage:
    """Integration-style test: two-column page with full-width interruption."""

    def test_column_interrupt_column_pattern(self) -> None:
        # Band 0: two columns of body text
        b0 = _band("b0", _bbox(0.05, 0.08, 0.95, 0.35), 0, 2)
        c0 = _column(
            "c0",
            _bbox(0.05, 0.08, 0.47, 0.35),
            band_index=0,
            column_index=0,
            parent_id="b0",
        )
        c1 = _column(
            "c1",
            _bbox(0.53, 0.08, 0.95, 0.35),
            band_index=0,
            column_index=1,
            parent_id="b0",
        )

        # Band 1: full-width figure
        b1 = _band("b1", _bbox(0.10, 0.38, 0.90, 0.55), 1, 1)
        fig = _figure(
            "fig0",
            _bbox(0.15, 0.39, 0.85, 0.54),
            band_index=1,
            parent_id="b1",
        )

        # Band 2: two columns resume
        b2 = _band("b2", _bbox(0.05, 0.58, 0.95, 0.90), 2, 2)
        c2 = _column(
            "c2",
            _bbox(0.05, 0.58, 0.47, 0.90),
            band_index=2,
            column_index=0,
            parent_id="b2",
        )
        c3 = _column(
            "c3",
            _bbox(0.53, 0.58, 0.95, 0.90),
            band_index=2,
            column_index=1,
            parent_id="b2",
        )

        graph = _graph(
            [b0, c0, c1, b1, fig, b2, c2, c3],
            [
                _contains("b0", "c0"),
                _contains("b0", "c1"),
                _adjacent("b0", "b1"),
                _contains("b1", "fig0"),
                _adjacent("b1", "b2"),
                _contains("b2", "c2"),
                _contains("b2", "c3"),
            ],
        )
        order = compute_reading_order(graph)

        # Expected order: left col, right col, full-width band, figure, left col, right col
        ids = [e.region_id for e in order.entries]
        assert ids == ["c0", "c1", "b1", "fig0", "c2", "c3"]

        # Full-width band is interruption
        b1_entry = next(e for e in order.entries if e.region_id == "b1")
        assert b1_entry.flow_role == "interruption"

        # Figure inside interruption band is main flow
        fig_entry = next(e for e in order.entries if e.region_id == "fig0")
        assert fig_entry.flow_role == "main"

        # No unassigned regions (bands with columns are structural)
        assert order.unassigned_region_ids == []
        assert order.total_regions == 8
