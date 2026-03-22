from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import (
    FigureBlock,
    HeadingBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.utils.architecture_compare import (
    PageComparisonResult,
    build_comparison_report,
    compare_page_outputs,
)


def _make_page(
    page_number: int,
    blocks: list[ParagraphBlock | HeadingBlock | FigureBlock],
    *,
    render_mode: str = "semantic",
) -> PageRecord:
    return PageRecord(
        page_number=page_number,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        render_mode=render_mode,
        blocks=blocks,
    )


class TestComparePageOutputs:
    def test_block_counts_and_delta(self) -> None:
        v2 = _make_page(
            1,
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="hello")]),
                ParagraphBlock(block_id="p2", content=[TextRun(text="world")]),
            ],
        )
        v3 = _make_page(
            1,
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="hello")]),
                HeadingBlock(block_id="h1", content=[TextRun(text="Title")]),
                FigureBlock(block_id="f1", asset_ref="img.png"),
            ],
        )

        result = compare_page_outputs(v2, v3, v3_confidence=0.9)

        assert result.v2_block_count == 2
        assert result.v3_block_count == 3
        assert result.block_count_delta == 1

    def test_kind_counts(self) -> None:
        v2 = _make_page(
            1,
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="a")]),
                ParagraphBlock(block_id="p2", content=[TextRun(text="b")]),
            ],
        )
        v3 = _make_page(
            1,
            [
                HeadingBlock(block_id="h1", content=[TextRun(text="T")]),
                FigureBlock(block_id="f1", asset_ref="x.png"),
            ],
        )

        result = compare_page_outputs(v2, v3)

        assert result.v2_kind_counts == {"paragraph": 2}
        assert result.v3_kind_counts == {"heading": 1, "figure": 1}

    def test_kinds_only_in_fields(self) -> None:
        v2 = _make_page(
            1,
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="a")]),
                FigureBlock(block_id="f1", asset_ref="x.png"),
            ],
        )
        v3 = _make_page(
            1,
            [
                ParagraphBlock(block_id="p1", content=[TextRun(text="a")]),
                HeadingBlock(block_id="h1", content=[TextRun(text="T")]),
            ],
        )

        result = compare_page_outputs(v2, v3)

        assert result.kinds_only_in_v2 == ["figure"]
        assert result.kinds_only_in_v3 == ["heading"]

    def test_render_mode_propagated(self) -> None:
        v2 = _make_page(1, [])
        v3 = _make_page(1, [], render_mode="facsimile")

        result = compare_page_outputs(v2, v3)

        assert result.v3_render_mode == "facsimile"


class TestBuildComparisonReport:
    def test_avg_stats(self) -> None:
        pages = [
            PageComparisonResult(
                page_number=1,
                v2_block_count=4,
                v3_block_count=6,
                block_count_delta=2,
                v3_confidence=0.8,
                v3_render_mode="semantic",
            ),
            PageComparisonResult(
                page_number=2,
                v2_block_count=2,
                v3_block_count=4,
                block_count_delta=2,
                v3_confidence=1.0,
                v3_render_mode="facsimile",
            ),
        ]

        report = build_comparison_report("test-doc", pages)

        assert report.doc_id == "test-doc"
        assert report.total_pages == 2
        assert report.avg_v2_blocks == 3.0
        assert report.avg_v3_blocks == 5.0
        assert report.avg_block_delta == 2.0
        assert report.avg_v3_confidence == 0.9

    def test_route_counts(self) -> None:
        pages = [
            PageComparisonResult(page_number=1, v3_render_mode="semantic"),
            PageComparisonResult(page_number=2, v3_render_mode="semantic"),
            PageComparisonResult(page_number=3, v3_render_mode="facsimile"),
        ]

        report = build_comparison_report("doc-2", pages)

        assert report.v3_route_counts == {"semantic": 2, "facsimile": 1}

    def test_empty_pages(self) -> None:
        report = build_comparison_report("empty-doc", [])

        assert report.total_pages == 0
        assert report.pages == []
        assert report.avg_v2_blocks == 0.0
