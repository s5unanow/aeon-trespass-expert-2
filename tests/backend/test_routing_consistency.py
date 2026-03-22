"""Fallback-routing consistency tests for confidence-driven page outcomes.

Verifies that curated fixture pages route to the expected render mode
(semantic, hybrid, facsimile) deterministically, and that non-semantic
routes carry the required fallback assets and confidence reasons.

Introduced by S5U-280.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from aeon_reader_pipeline.models.evidence_models import PrimitivePageEvidence
from aeon_reader_pipeline.stages.confidence import (
    HYBRID_THRESHOLD,
    SEMANTIC_THRESHOLD,
)
from tests.backend.evidence_helpers import run_evidence_pipeline
from tests.backend.test_evidence_goldens import (
    _build_layout_extreme,
    _build_mixed_hard,
    _build_simple_semantic,
)

# ---------------------------------------------------------------------------
# Expected route declarations per fixture
# ---------------------------------------------------------------------------
# Each mapping: page_number -> expected render mode.
# These are the authoritative expectations for CI regression checking.

SIMPLE_SEMANTIC_EXPECTED: dict[int, str] = {
    1: "semantic",
    2: "semantic",
}

MIXED_HARD_EXPECTED: dict[int, str] = {
    1: "hybrid",
    2: "hybrid",
    3: "hybrid",
    4: "hybrid",
}

LAYOUT_EXTREME_EXPECTED: dict[int, str] = {
    1: "hybrid",
    2: "hybrid",
    3: "hybrid",
    4: "hybrid",
}

_FIXTURES: list[tuple[str, Callable[[], list[PrimitivePageEvidence]], dict[int, str]]] = [
    ("simple_semantic", _build_simple_semantic, SIMPLE_SEMANTIC_EXPECTED),
    ("mixed_hard", _build_mixed_hard, MIXED_HARD_EXPECTED),
    ("layout_extreme", _build_layout_extreme, LAYOUT_EXTREME_EXPECTED),
]


# ---------------------------------------------------------------------------
# Route outcome tests
# ---------------------------------------------------------------------------


class TestRouteOutcomes:
    """Each fixture page routes to its declared expected render mode."""

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_route_matches_expectation(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, expected_route in expected.items():
            actual = result.routes[pn]
            assert actual == expected_route, (
                f"{name} p{pn}: expected route '{expected_route}', "
                f"got '{actual}' (confidence={result.confidences[pn][0]:.3f})"
            )

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_all_pages_covered(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        """Every page produced by the fixture has an expected route declaration."""
        result = run_evidence_pipeline(builder())
        for pn in result.routes:
            assert pn in expected, f"{name} p{pn}: missing expected route declaration"


# ---------------------------------------------------------------------------
# Fallback asset tests for non-semantic routes
# ---------------------------------------------------------------------------


class TestFallbackAssets:
    """Non-semantic routes carry required fallback_image_ref and confidence reasons."""

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_non_semantic_has_fallback_image_ref(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            resolved = result.resolved[pn]
            if route != "semantic":
                assert resolved.fallback_image_ref is not None, (
                    f"{name} p{pn}: route '{route}' but fallback_image_ref is None"
                )
                assert resolved.fallback_image_ref == f"p{pn:04d}_fallback.png", (
                    f"{name} p{pn}: unexpected fallback_image_ref '{resolved.fallback_image_ref}'"
                )
            else:
                assert resolved.fallback_image_ref is None, (
                    f"{name} p{pn}: semantic route should not have fallback_image_ref"
                )

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_non_semantic_has_confidence_reasons(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            resolved = result.resolved[pn]
            if route != "semantic":
                assert len(resolved.confidence_reasons) > 0, (
                    f"{name} p{pn}: route '{route}' but confidence_reasons is empty"
                )

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_render_mode_matches_resolved(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        """ResolvedPageIR.render_mode matches the route from confidence scoring."""
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            resolved = result.resolved[pn]
            assert resolved.render_mode == route, (
                f"{name} p{pn}: resolved.render_mode '{resolved.render_mode}' "
                f"!= expected route '{route}'"
            )


# ---------------------------------------------------------------------------
# Confidence-threshold consistency
# ---------------------------------------------------------------------------


class TestConfidenceThresholdConsistency:
    """Confidence scores are consistent with routing thresholds."""

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_semantic_confidence_at_or_above_threshold(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            score = result.confidences[pn][0]
            if route == "semantic":
                assert score >= SEMANTIC_THRESHOLD, (
                    f"{name} p{pn}: semantic but confidence {score:.3f} "
                    f"< threshold {SEMANTIC_THRESHOLD}"
                )

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_hybrid_confidence_in_range(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            score = result.confidences[pn][0]
            if route == "hybrid":
                assert HYBRID_THRESHOLD <= score < SEMANTIC_THRESHOLD, (
                    f"{name} p{pn}: hybrid but confidence {score:.3f} "
                    f"not in [{HYBRID_THRESHOLD}, {SEMANTIC_THRESHOLD})"
                )

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_facsimile_confidence_below_hybrid(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        result = run_evidence_pipeline(builder())
        for pn, route in expected.items():
            score = result.confidences[pn][0]
            if route == "facsimile":
                assert score < HYBRID_THRESHOLD, (
                    f"{name} p{pn}: facsimile but confidence {score:.3f} "
                    f">= threshold {HYBRID_THRESHOLD}"
                )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestRoutingDeterminism:
    """Running the same fixture twice produces identical routing decisions."""

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_deterministic_routes(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        pages = builder()
        r1 = run_evidence_pipeline(pages)
        r2 = run_evidence_pipeline(pages)
        for pn in r1.routes:
            assert r1.routes[pn] == r2.routes[pn], (
                f"{name} p{pn}: non-deterministic route ({r1.routes[pn]} vs {r2.routes[pn]})"
            )
            s1, reasons1 = r1.confidences[pn]
            s2, reasons2 = r2.confidences[pn]
            assert s1 == s2, f"{name} p{pn}: non-deterministic confidence ({s1} vs {s2})"
            assert reasons1 == reasons2, f"{name} p{pn}: non-deterministic reasons"

    @pytest.mark.parametrize(
        ("name", "builder", "expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_deterministic_fallback_refs(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        expected: dict[int, str],
    ) -> None:
        pages = builder()
        r1 = run_evidence_pipeline(pages)
        r2 = run_evidence_pipeline(pages)
        for pn in r1.resolved:
            ref1 = r1.resolved[pn].fallback_image_ref
            ref2 = r2.resolved[pn].fallback_image_ref
            assert ref1 == ref2, (
                f"{name} p{pn}: non-deterministic fallback_image_ref ({ref1} vs {ref2})"
            )


# ---------------------------------------------------------------------------
# Cross-fixture confidence ordering
# ---------------------------------------------------------------------------


class TestCrossFixtureOrdering:
    """More complex fixtures have lower average confidence than simpler ones."""

    def test_simple_gt_mixed_gt_extreme(self) -> None:
        simple = run_evidence_pipeline(_build_simple_semantic())
        mixed = run_evidence_pipeline(_build_mixed_hard())
        extreme = run_evidence_pipeline(_build_layout_extreme())

        avg_simple = sum(s for s, _ in simple.confidences.values()) / len(simple.confidences)
        avg_mixed = sum(s for s, _ in mixed.confidences.values()) / len(mixed.confidences)
        avg_extreme = sum(s for s, _ in extreme.confidences.values()) / len(extreme.confidences)

        assert avg_simple > avg_mixed, f"simple ({avg_simple:.3f}) should > mixed ({avg_mixed:.3f})"
        assert avg_mixed > avg_extreme, (
            f"mixed ({avg_mixed:.3f}) should > extreme ({avg_extreme:.3f})"
        )
