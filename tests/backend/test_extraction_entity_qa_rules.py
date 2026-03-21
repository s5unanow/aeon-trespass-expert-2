"""Tests for extraction and entity QA rules (S5U-278)."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    NormalizedBBox,
    PageReadingOrder,
    PageRegionGraph,
    ReadingOrderEntry,
    RegionCandidate,
    RegionEdge,
)
from aeon_reader_pipeline.models.ir_models import (
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    PageRecord,
    ParagraphBlock,
    SymbolRef,
    TableBlock,
    TableCell,
    TextRun,
)
from aeon_reader_pipeline.qa.rules.entity_rules import (
    CalloutStructureRule,
    FigureCaptionLinkageRule,
    TableStructureRule,
)
from aeon_reader_pipeline.qa.rules.extraction_rules import (
    ReadingOrderValidityRule,
    RegionGraphValidityRule,
)
from aeon_reader_pipeline.qa.rules.symbol_rules import SymbolAnchorValidityRule

_BBOX = NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)


def _page(
    blocks: list[object],
    page_number: int = 1,
    render_mode: str = "semantic",
) -> PageRecord:
    return PageRecord(
        page_number=page_number,
        doc_id="doc",
        width_pt=612,
        height_pt=792,
        render_mode=render_mode,
        blocks=blocks,  # type: ignore[arg-type]
    )


def _region(region_id: str, kind: str = "main_flow") -> RegionCandidate:
    return RegionCandidate(region_id=region_id, kind_hint=kind, bbox=_BBOX)  # type: ignore[arg-type]


def _evidence(
    page_number: int = 1,
    regions: list[RegionCandidate] | None = None,
    edges: list[RegionEdge] | None = None,
    entries: list[ReadingOrderEntry] | None = None,
    unassigned: list[str] | None = None,
) -> CanonicalPageEvidence:
    region_graph = PageRegionGraph(
        page_number=page_number,
        doc_id="doc",
        width_pt=612,
        height_pt=792,
        regions=regions or [],
        edges=edges or [],
    )
    reading_order = PageReadingOrder(
        page_number=page_number,
        doc_id="doc",
        entries=entries or [],
        total_regions=len(regions) if regions else 0,
        unassigned_region_ids=unassigned or [],
    )
    return CanonicalPageEvidence(
        page_number=page_number,
        doc_id="doc",
        width_pt=612,
        height_pt=792,
        region_graph=region_graph,
        reading_order=reading_order,
    )


# ---------------------------------------------------------------------------
# RegionGraphValidityRule
# ---------------------------------------------------------------------------


class TestRegionGraphValidityRule:
    def test_valid_graph_no_issues(self) -> None:
        ev = _evidence(
            regions=[_region("r1"), _region("r2")],
            edges=[RegionEdge(edge_type="adjacent_to", src_region_id="r1", dst_region_id="r2")],
        )
        rule = RegionGraphValidityRule({1: ev})
        assert rule.check([_page([])], None) == []

    def test_duplicate_region_id(self) -> None:
        ev = _evidence(regions=[_region("r1"), _region("r1")])
        rule = RegionGraphValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "Duplicate region ID" in issues[0].message

    def test_edge_references_unknown_source(self) -> None:
        ev = _evidence(
            regions=[_region("r1")],
            edges=[RegionEdge(edge_type="contains", src_region_id="rx", dst_region_id="r1")],
        )
        rule = RegionGraphValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert any("source 'rx'" in i.message for i in issues)

    def test_edge_references_unknown_destination(self) -> None:
        ev = _evidence(
            regions=[_region("r1")],
            edges=[RegionEdge(edge_type="contains", src_region_id="r1", dst_region_id="rx")],
        )
        rule = RegionGraphValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert any("destination 'rx'" in i.message for i in issues)

    def test_self_referential_edge(self) -> None:
        ev = _evidence(
            regions=[_region("r1")],
            edges=[RegionEdge(edge_type="contains", src_region_id="r1", dst_region_id="r1")],
        )
        rule = RegionGraphValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert any("Self-referential" in i.message for i in issues)

    def test_skips_pages_without_evidence(self) -> None:
        rule = RegionGraphValidityRule({})
        assert rule.check([_page([])], None) == []

    def test_skips_pages_without_region_graph(self) -> None:
        ev = CanonicalPageEvidence(
            page_number=1, doc_id="doc", width_pt=612, height_pt=792, region_graph=None
        )
        rule = RegionGraphValidityRule({1: ev})
        assert rule.check([_page([])], None) == []


# ---------------------------------------------------------------------------
# ReadingOrderValidityRule
# ---------------------------------------------------------------------------


class TestReadingOrderValidityRule:
    def test_valid_order_no_issues(self) -> None:
        ev = _evidence(
            regions=[_region("r1"), _region("r2")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
                ReadingOrderEntry(sequence_index=1, region_id="r2", kind_hint="column"),
            ],
        )
        rule = ReadingOrderValidityRule({1: ev})
        assert rule.check([_page([])], None) == []

    def test_non_contiguous_indices(self) -> None:
        ev = _evidence(
            regions=[_region("r1"), _region("r2")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
                ReadingOrderEntry(sequence_index=5, region_id="r2", kind_hint="column"),
            ],
        )
        rule = ReadingOrderValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert any("Non-contiguous" in i.message for i in issues)
        assert issues[0].severity == "error"

    def test_references_unknown_region(self) -> None:
        ev = _evidence(
            regions=[_region("r1")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
                ReadingOrderEntry(sequence_index=1, region_id="rx", kind_hint="column"),
            ],
        )
        rule = ReadingOrderValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert any("unknown region" in i.message for i in issues)

    def test_unassigned_regions_warning(self) -> None:
        ev = _evidence(
            regions=[_region("r1"), _region("r2")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
            ],
            unassigned=["r2"],
        )
        rule = ReadingOrderValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "unassigned" in issues[0].message

    def test_skips_pages_without_reading_order(self) -> None:
        ev = CanonicalPageEvidence(
            page_number=1, doc_id="doc", width_pt=612, height_pt=792, reading_order=None
        )
        rule = ReadingOrderValidityRule({1: ev})
        assert rule.check([_page([])], None) == []


# ---------------------------------------------------------------------------
# SymbolAnchorValidityRule
# ---------------------------------------------------------------------------


class TestSymbolAnchorValidityRule:
    def test_valid_symbol_ref(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[SymbolRef(symbol_id="health", alt_text="HP")],
                ),
            ]
        )
        rule = SymbolAnchorValidityRule()
        assert rule.check([page], None) == []

    def test_empty_symbol_id_is_error(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[SymbolRef(symbol_id="", alt_text="?")],
                ),
            ]
        )
        rule = SymbolAnchorValidityRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].rule_id == "symbol.anchor_validity"

    def test_skips_facsimile_pages(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[SymbolRef(symbol_id="", alt_text="?")],
                ),
            ],
            render_mode="facsimile",
        )
        rule = SymbolAnchorValidityRule()
        assert rule.check([page], None) == []

    def test_text_runs_ignored(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="hello")],
                ),
            ]
        )
        rule = SymbolAnchorValidityRule()
        assert rule.check([page], None) == []


# ---------------------------------------------------------------------------
# FigureCaptionLinkageRule
# ---------------------------------------------------------------------------


class TestFigureCaptionLinkageRule:
    def test_valid_linkage(self) -> None:
        page = _page(
            [
                FigureBlock(block_id="fig1", caption_block_id="cap1"),
                CaptionBlock(block_id="cap1", parent_block_id="fig1"),
            ]
        )
        rule = FigureCaptionLinkageRule()
        assert rule.check([page], None) == []

    def test_figure_references_missing_caption(self) -> None:
        page = _page([FigureBlock(block_id="fig1", caption_block_id="cap_gone")])
        rule = FigureCaptionLinkageRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "missing caption" in issues[0].message

    def test_caption_references_missing_parent(self) -> None:
        page = _page([CaptionBlock(block_id="cap1", parent_block_id="fig_gone")])
        rule = FigureCaptionLinkageRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "missing parent" in issues[0].message

    def test_figure_without_caption_ok(self) -> None:
        page = _page([FigureBlock(block_id="fig1")])
        rule = FigureCaptionLinkageRule()
        assert rule.check([page], None) == []

    def test_caption_without_parent_ok(self) -> None:
        page = _page([CaptionBlock(block_id="cap1")])
        rule = FigureCaptionLinkageRule()
        assert rule.check([page], None) == []

    def test_caption_parent_wrong_block_type(self) -> None:
        page = _page(
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="text")]),
                CaptionBlock(block_id="cap1", parent_block_id="p1"),
            ]
        )
        rule = FigureCaptionLinkageRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "not a FigureBlock or TableBlock" in issues[0].message

    def test_caption_parent_table_ok(self) -> None:
        page = _page(
            [
                TableBlock(
                    block_id="t1", rows=1, cols=1, cells=[TableCell(row=0, col=0, text="A")]
                ),
                CaptionBlock(block_id="cap1", parent_block_id="t1"),
            ]
        )
        rule = FigureCaptionLinkageRule()
        assert rule.check([page], None) == []

    def test_skips_facsimile_pages(self) -> None:
        page = _page(
            [FigureBlock(block_id="fig1", caption_block_id="cap_gone")],
            render_mode="facsimile",
        )
        rule = FigureCaptionLinkageRule()
        assert rule.check([page], None) == []


# ---------------------------------------------------------------------------
# TableStructureRule
# ---------------------------------------------------------------------------


class TestTableStructureRule:
    def test_valid_table(self) -> None:
        page = _page(
            [
                TableBlock(
                    block_id="t1",
                    rows=2,
                    cols=2,
                    cells=[
                        TableCell(row=0, col=0, text="A"),
                        TableCell(row=0, col=1, text="B"),
                        TableCell(row=1, col=0, text="C"),
                        TableCell(row=1, col=1, text="D"),
                    ],
                ),
            ]
        )
        rule = TableStructureRule()
        assert rule.check([page], None) == []

    def test_empty_cells_with_dimensions(self) -> None:
        page = _page([TableBlock(block_id="t1", rows=2, cols=3)])
        rule = TableStructureRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "no cells" in issues[0].message

    def test_cell_row_out_of_bounds(self) -> None:
        page = _page(
            [
                TableBlock(
                    block_id="t1",
                    rows=2,
                    cols=2,
                    cells=[TableCell(row=5, col=0, text="bad")],
                ),
            ]
        )
        rule = TableStructureRule()
        issues = rule.check([page], None)
        assert any("cell row 5" in i.message for i in issues)

    def test_cell_col_out_of_bounds(self) -> None:
        page = _page(
            [
                TableBlock(
                    block_id="t1",
                    rows=2,
                    cols=2,
                    cells=[TableCell(row=0, col=9, text="bad")],
                ),
            ]
        )
        rule = TableStructureRule()
        issues = rule.check([page], None)
        assert any("cell col 9" in i.message for i in issues)

    def test_zero_dimensions_no_cells_ok(self) -> None:
        page = _page([TableBlock(block_id="t1", rows=0, cols=0)])
        rule = TableStructureRule()
        assert rule.check([page], None) == []

    def test_skips_facsimile_pages(self) -> None:
        page = _page(
            [TableBlock(block_id="t1", rows=2, cols=3)],
            render_mode="facsimile",
        )
        rule = TableStructureRule()
        assert rule.check([page], None) == []


# ---------------------------------------------------------------------------
# CalloutStructureRule
# ---------------------------------------------------------------------------


class TestCalloutStructureRule:
    def test_valid_callout(self) -> None:
        page = _page([CalloutBlock(block_id="c1", content=[TextRun(text="Note")])])
        rule = CalloutStructureRule()
        assert rule.check([page], None) == []

    def test_empty_callout_is_warning(self) -> None:
        page = _page([CalloutBlock(block_id="c1")])
        rule = CalloutStructureRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "empty content" in issues[0].message

    def test_skips_facsimile_pages(self) -> None:
        page = _page(
            [CalloutBlock(block_id="c1")],
            render_mode="facsimile",
        )
        rule = CalloutStructureRule()
        assert rule.check([page], None) == []


# ---------------------------------------------------------------------------
# Integration: valid fixtures pass, bad fixtures produce blocking errors
# ---------------------------------------------------------------------------


class TestIntegrationErrorsOnBadFixtures:
    """Verify that intentionally bad artifacts produce blocking errors."""

    def test_bad_region_graph_produces_errors(self) -> None:
        ev = _evidence(
            regions=[_region("r1"), _region("r1")],
            edges=[RegionEdge(edge_type="contains", src_region_id="r1", dst_region_id="r1")],
        )
        rule = RegionGraphValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 2  # duplicate + self-ref

    def test_bad_reading_order_produces_errors(self) -> None:
        ev = _evidence(
            regions=[_region("r1")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
                ReadingOrderEntry(sequence_index=3, region_id="ghost", kind_hint="column"),
            ],
        )
        rule = ReadingOrderValidityRule({1: ev})
        issues = rule.check([_page([])], None)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) >= 2  # non-contiguous + unknown region

    def test_valid_fixture_passes_all_rules(self) -> None:
        """A well-formed page with valid evidence produces zero errors."""
        ev = _evidence(
            regions=[_region("r1"), _region("r2")],
            entries=[
                ReadingOrderEntry(sequence_index=0, region_id="r1", kind_hint="main_flow"),
                ReadingOrderEntry(sequence_index=1, region_id="r2", kind_hint="column"),
            ],
        )
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[
                        TextRun(text="Hello", ru_text="Привет"),
                        SymbolRef(symbol_id="health", alt_text="HP"),
                    ],
                ),
                FigureBlock(block_id="fig1", caption_block_id="cap1"),
                CaptionBlock(
                    block_id="cap1",
                    parent_block_id="fig1",
                    content=[TextRun(text="Fig 1", ru_text="Рис 1")],
                ),
                TableBlock(
                    block_id="t1",
                    rows=1,
                    cols=2,
                    cells=[
                        TableCell(row=0, col=0, text="A"),
                        TableCell(row=0, col=1, text="B"),
                    ],
                ),
                CalloutBlock(
                    block_id="c1",
                    content=[TextRun(text="Tip", ru_text="Совет")],
                ),
            ]
        )

        all_issues: list[object] = []
        all_issues.extend(RegionGraphValidityRule({1: ev}).check([page], None))
        all_issues.extend(ReadingOrderValidityRule({1: ev}).check([page], None))
        all_issues.extend(SymbolAnchorValidityRule().check([page], None))
        all_issues.extend(FigureCaptionLinkageRule().check([page], None))
        all_issues.extend(TableStructureRule().check([page], None))
        all_issues.extend(CalloutStructureRule().check([page], None))

        assert all_issues == []
