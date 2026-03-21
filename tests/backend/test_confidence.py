"""Tests for page confidence scoring and fallback-routing policy (S5U-263)."""

from __future__ import annotations

import pytest

from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    PageReadingOrder,
    PageRegionGraph,
    ReadingOrderEntry,
    RegionCandidate,
    RegionConfidence,
    ResolvedPageIR,
)
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.qa.rules.confidence_rules import LowConfidencePageRule
from aeon_reader_pipeline.stages.confidence import (
    HYBRID_THRESHOLD,
    SEMANTIC_THRESHOLD,
    route_page,
    score_page_confidence,
)


def _minimal_canonical(**overrides: object) -> CanonicalPageEvidence:
    """Build a minimal CanonicalPageEvidence with sensible defaults."""
    defaults: dict[str, object] = {
        "page_number": 1,
        "doc_id": "test",
        "width_pt": 612.0,
        "height_pt": 792.0,
    }
    defaults.update(overrides)
    return CanonicalPageEvidence(**defaults)  # type: ignore[arg-type]


def _region(
    region_id: str = "r1",
    kind_hint: str = "main_flow",
    confidence: float = 1.0,
) -> RegionCandidate:
    from aeon_reader_pipeline.models.evidence_models import NormalizedBBox

    return RegionCandidate(
        region_id=region_id,
        kind_hint=kind_hint,  # type: ignore[arg-type]
        bbox=NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
        confidence=RegionConfidence(value=confidence),
    )


def _reading_order_entry(
    index: int = 0,
    region_id: str = "r1",
    confidence: float = 1.0,
) -> ReadingOrderEntry:
    return ReadingOrderEntry(
        sequence_index=index,
        region_id=region_id,
        kind_hint="main_flow",
        confidence=RegionConfidence(value=confidence),
    )


# ---------------------------------------------------------------------------
# Routing thresholds
# ---------------------------------------------------------------------------


class TestRoutePageThresholds:
    def test_high_confidence_is_semantic(self) -> None:
        assert route_page(1.0) == "semantic"
        assert route_page(0.8) == "semantic"
        assert route_page(SEMANTIC_THRESHOLD) == "semantic"

    def test_mid_confidence_is_hybrid(self) -> None:
        assert route_page(0.59) == "hybrid"
        assert route_page(0.4) == "hybrid"
        assert route_page(HYBRID_THRESHOLD) == "hybrid"

    def test_low_confidence_is_facsimile(self) -> None:
        assert route_page(0.29) == "facsimile"
        assert route_page(0.1) == "facsimile"
        assert route_page(0.0) == "facsimile"


# ---------------------------------------------------------------------------
# Scoring — simple page (no evidence)
# ---------------------------------------------------------------------------


class TestScoreSimplePage:
    def test_empty_evidence_scores_perfect(self) -> None:
        canonical = _minimal_canonical()
        score, reasons = score_page_confidence(canonical)
        assert score == 1.0
        assert reasons == []

    def test_single_column_no_entities(self) -> None:
        canonical = _minimal_canonical(estimated_column_count=1)
        score, _ = score_page_confidence(canonical)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Scoring — region confidence
# ---------------------------------------------------------------------------


class TestScoreRegionConfidence:
    def test_low_region_confidence_penalizes(self) -> None:
        rg = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            regions=[_region(confidence=0.5)],
        )
        canonical = _minimal_canonical(region_graph=rg)
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("region_confidence_min" in r for r in reasons)

    def test_perfect_region_confidence_no_penalty(self) -> None:
        rg = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            regions=[_region(confidence=1.0)],
        )
        canonical = _minimal_canonical(region_graph=rg)
        score, _reasons = score_page_confidence(canonical)
        assert score == 1.0


# ---------------------------------------------------------------------------
# Scoring — reading order
# ---------------------------------------------------------------------------


class TestScoreReadingOrder:
    def test_low_reading_order_confidence_penalizes(self) -> None:
        ro = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[_reading_order_entry(confidence=0.4)],
            total_regions=1,
        )
        canonical = _minimal_canonical(reading_order=ro)
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("reading_order_confidence_min" in r for r in reasons)

    def test_unassigned_regions_penalize(self) -> None:
        ro = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[_reading_order_entry()],
            total_regions=4,
            unassigned_region_ids=["r2", "r3", "r4"],
        )
        canonical = _minimal_canonical(reading_order=ro)
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("unassigned_region_fraction" in r for r in reasons)


# ---------------------------------------------------------------------------
# Scoring — layout complexity
# ---------------------------------------------------------------------------


class TestScoreLayoutComplexity:
    def test_two_columns_penalizes(self) -> None:
        canonical = _minimal_canonical(estimated_column_count=2)
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("column_count=2" in r for r in reasons)

    def test_three_columns_penalizes_more(self) -> None:
        c2 = _minimal_canonical(estimated_column_count=2)
        c3 = _minimal_canonical(estimated_column_count=3)
        s2, _ = score_page_confidence(c2)
        s3, _ = score_page_confidence(c3)
        assert s3 < s2

    def test_entity_density_penalizes(self) -> None:
        canonical = _minimal_canonical(
            has_tables=True,
            has_figures=True,
            has_callouts=True,
        )
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("entity_density" in r for r in reasons)


# ---------------------------------------------------------------------------
# Scoring — furniture
# ---------------------------------------------------------------------------


class TestScoreFurniture:
    def test_high_furniture_penalizes(self) -> None:
        canonical = _minimal_canonical(furniture_fraction=0.8)
        score, reasons = score_page_confidence(canonical)
        assert score < 1.0
        assert any("furniture_fraction" in r for r in reasons)

    def test_low_furniture_no_penalty(self) -> None:
        canonical = _minimal_canonical(furniture_fraction=0.3)
        _score, reasons = score_page_confidence(canonical)
        # furniture_fraction <= 0.5 should not penalize
        assert not any("furniture_fraction" in r for r in reasons)


# ---------------------------------------------------------------------------
# Scoring — combined signals trigger routing
# ---------------------------------------------------------------------------


class TestScoreRouting:
    def test_many_penalties_drop_to_hybrid(self) -> None:
        rg = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            regions=[_region(confidence=0.3)],
        )
        ro = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[_reading_order_entry(confidence=0.3)],
            total_regions=1,
        )
        canonical = _minimal_canonical(
            region_graph=rg,
            reading_order=ro,
            estimated_column_count=2,
            has_tables=True,
        )
        score, _ = score_page_confidence(canonical)
        mode = route_page(score)
        assert mode in ("hybrid", "facsimile")

    def test_extreme_penalties_drop_to_facsimile(self) -> None:
        rg = PageRegionGraph(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            regions=[_region(confidence=0.0)],
        )
        ro = PageReadingOrder(
            page_number=1,
            doc_id="test",
            entries=[_reading_order_entry(confidence=0.0)],
            total_regions=5,
            unassigned_region_ids=["r2", "r3", "r4", "r5"],
        )
        canonical = _minimal_canonical(
            region_graph=rg,
            reading_order=ro,
            estimated_column_count=3,
            has_tables=True,
            has_figures=True,
            has_callouts=True,
            furniture_fraction=0.9,
        )
        score, reasons = score_page_confidence(canonical)
        mode = route_page(score)
        assert mode == "facsimile"
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# Score is deterministic
# ---------------------------------------------------------------------------


class TestScoreDeterminism:
    def test_same_inputs_same_output(self) -> None:
        canonical = _minimal_canonical(
            estimated_column_count=2,
            has_tables=True,
        )
        s1, r1 = score_page_confidence(canonical)
        s2, r2 = score_page_confidence(canonical)
        assert s1 == s2
        assert r1 == r2


# ---------------------------------------------------------------------------
# Score clamped to [0, 1]
# ---------------------------------------------------------------------------


class TestScoreBounds:
    @pytest.mark.parametrize("cols", [1, 2, 3])
    def test_score_in_bounds(self, cols: int) -> None:
        canonical = _minimal_canonical(
            estimated_column_count=cols,
            has_tables=True,
            has_figures=True,
            has_callouts=True,
            furniture_fraction=0.95,
        )
        score, _ = score_page_confidence(canonical)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# ResolvedPageIR contract
# ---------------------------------------------------------------------------


class TestResolvedPageIRContract:
    def test_confidence_field_accepts_range(self) -> None:
        ir = ResolvedPageIR(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            page_confidence=0.45,
            confidence_reasons=["column_count=2 (penalty=0.045)"],
            render_mode="hybrid",
        )
        assert ir.page_confidence == 0.45
        assert ir.render_mode == "hybrid"
        assert len(ir.confidence_reasons) == 1


# ---------------------------------------------------------------------------
# QA rule — LowConfidencePageRule
# ---------------------------------------------------------------------------


class TestLowConfidencePageRule:
    def _page(self, render_mode: str = "semantic") -> PageRecord:
        return PageRecord(
            page_number=1,
            doc_id="test",
            width_pt=612.0,
            height_pt=792.0,
            render_mode=render_mode,  # type: ignore[arg-type]
        )

    def test_semantic_no_issue(self) -> None:
        rule = LowConfidencePageRule()
        issues = rule.check([self._page("semantic")], None)
        assert issues == []

    def test_hybrid_warning(self) -> None:
        rule = LowConfidencePageRule()
        issues = rule.check([self._page("hybrid")], None)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].rule_id == "confidence.low_page"

    def test_facsimile_info(self) -> None:
        rule = LowConfidencePageRule()
        issues = rule.check([self._page("facsimile")], None)
        assert len(issues) == 1
        assert issues[0].severity == "info"

    def test_mixed_pages(self) -> None:
        rule = LowConfidencePageRule()
        pages = [
            self._page("semantic"),
            self._page("hybrid"),
            self._page("facsimile"),
        ]
        issues = rule.check(pages, None)
        assert len(issues) == 2
