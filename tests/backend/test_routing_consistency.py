"""Fallback-routing consistency tests for confidence-driven page outcomes.

Verifies that curated fixture pages route to the expected render mode
(semantic, hybrid, facsimile) deterministically, and that non-semantic
routes carry the required fallback assets and confidence reasons.

Complements test_evidence_goldens.py (which tests golden artifacts and
general invariants) with pinned route expectations and fallback-asset
assertions specific to the routing contract.

Introduced by S5U-280.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from aeon_reader_pipeline.models.evidence_models import PrimitivePageEvidence
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
# If confidence scoring changes, update these declarations explicitly.

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
# Route outcome tests — pinned expectations
# ---------------------------------------------------------------------------


class TestRouteOutcomes:
    """Each fixture page routes to its declared expected render mode.

    Unlike the golden tests (which compare full artifacts), these tests
    pin the high-level routing decision per page so that any confidence
    drift is caught immediately.
    """

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
# Determinism — fallback refs specifically
# ---------------------------------------------------------------------------
# Route/confidence determinism is already tested in test_evidence_goldens.py
# (TestEvidenceInvariants.test_deterministic). This class adds coverage for
# fallback_image_ref which is set by the helper but not in golden artifacts.


class TestFallbackDeterminism:
    """Fallback image refs are deterministic across runs."""

    @pytest.mark.parametrize(
        ("name", "builder", "_expected"),
        _FIXTURES,
        ids=[f[0] for f in _FIXTURES],
    )
    def test_deterministic_fallback_refs(
        self,
        name: str,
        builder: Callable[[], list[PrimitivePageEvidence]],
        _expected: dict[int, str],
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
