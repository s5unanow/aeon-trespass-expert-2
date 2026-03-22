"""Architecture v2/v3 output comparison utility.

Compares PageRecord outputs from v2 and v3 pipeline runs to quantify
differences in block counts, kind distributions, and v3-specific signals
(render mode, confidence).

Only imports from models/ — respects import boundaries.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.ir_models import PageRecord


class PageComparisonResult(BaseModel):
    """Per-page comparison between v2 and v3 pipeline outputs."""

    page_number: int

    # Block counts
    v2_block_count: int = 0
    v3_block_count: int = 0
    block_count_delta: int = 0

    # Kind distributions
    v2_kind_counts: dict[str, int] = Field(default_factory=dict)
    v3_kind_counts: dict[str, int] = Field(default_factory=dict)

    # V3-specific signals
    v3_render_mode: str = "semantic"
    v3_confidence: float = 1.0

    # Structural differences
    kinds_only_in_v2: list[str] = Field(default_factory=list)
    kinds_only_in_v3: list[str] = Field(default_factory=list)


class ArchitectureComparisonReport(BaseModel):
    """Aggregate comparison report across all pages."""

    doc_id: str
    total_pages: int = 0
    pages: list[PageComparisonResult] = Field(default_factory=list)

    # Summary stats
    avg_v2_blocks: float = 0.0
    avg_v3_blocks: float = 0.0
    avg_block_delta: float = 0.0
    avg_v3_confidence: float = 0.0

    # Route distribution
    v3_route_counts: dict[str, int] = Field(default_factory=dict)


def _count_block_kinds(page: PageRecord) -> dict[str, int]:
    """Count block kinds for a page."""
    counts: dict[str, int] = Counter()
    for block in page.blocks:
        counts[block.kind] += 1
    return dict(counts)


def compare_page_outputs(
    v2_page: PageRecord,
    v3_page: PageRecord,
    *,
    v3_confidence: float = 1.0,
) -> PageComparisonResult:
    """Compare a single page's v2 and v3 outputs."""
    v2_kinds = _count_block_kinds(v2_page)
    v3_kinds = _count_block_kinds(v3_page)

    v2_kind_set = set(v2_kinds)
    v3_kind_set = set(v3_kinds)

    return PageComparisonResult(
        page_number=v2_page.page_number,
        v2_block_count=len(v2_page.blocks),
        v3_block_count=len(v3_page.blocks),
        block_count_delta=len(v3_page.blocks) - len(v2_page.blocks),
        v2_kind_counts=v2_kinds,
        v3_kind_counts=v3_kinds,
        v3_render_mode=v3_page.render_mode,
        v3_confidence=v3_confidence,
        kinds_only_in_v2=sorted(v2_kind_set - v3_kind_set),
        kinds_only_in_v3=sorted(v3_kind_set - v2_kind_set),
    )


def build_comparison_report(
    doc_id: str,
    page_results: list[PageComparisonResult],
) -> ArchitectureComparisonReport:
    """Build an aggregate comparison report from per-page results."""
    total = len(page_results)
    if total == 0:
        return ArchitectureComparisonReport(doc_id=doc_id)

    route_counts: dict[str, int] = Counter()
    for p in page_results:
        route_counts[p.v3_render_mode] += 1

    return ArchitectureComparisonReport(
        doc_id=doc_id,
        total_pages=total,
        pages=page_results,
        avg_v2_blocks=sum(p.v2_block_count for p in page_results) / total,
        avg_v3_blocks=sum(p.v3_block_count for p in page_results) / total,
        avg_block_delta=sum(p.block_count_delta for p in page_results) / total,
        avg_v3_confidence=sum(p.v3_confidence for p in page_results) / total,
        v3_route_counts=dict(route_counts),
    )
