"""Golden tests for evidence pipeline end-to-end.

Runs synthetic multi-page fixtures through the full evidence pipeline
(furniture detection → asset registry → region segmentation → reading
order → canonical evidence → confidence scoring → routing) and compares
all intermediate artifacts against checked-in golden files.

Three fixture sets exercise different complexity levels:
  - simple_semantic:  low complexity → semantic route (>= 0.6)
  - mixed_hard:       medium complexity → hybrid route (0.3-0.6)
  - layout_extreme:   high complexity + high furniture → hybrid (lowest confidence)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import orjson
import pytest

from aeon_reader_pipeline.models.evidence_models import PrimitivePageEvidence
from tests.backend.builders import (
    drawing,
    image,
    page,
    table,
    text,
)
from tests.backend.evidence_helpers import EvidenceResult, run_evidence_pipeline

GOLDENS_DIR = Path(__file__).parent / "goldens" / "evidence"

# Set to True to regenerate golden files (run once, then set back to False)
_REGENERATE = False


# ---------------------------------------------------------------------------
# Golden file helpers
# ---------------------------------------------------------------------------


def _golden_path(fixture_name: str, artifact_name: str) -> Path:
    return GOLDENS_DIR / fixture_name / f"{artifact_name}.json"


def _serialize_model(model: Any) -> dict[str, Any]:
    """Serialize a Pydantic model, stripping run-specific fields."""
    data: dict[str, Any] = json.loads(
        orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    )
    data.pop("doc_id", None)
    data.pop("detection_version", None)
    return data


def _serialize_confidence(score: float, reasons: list[str], route: str) -> dict[str, Any]:
    return {"confidence": round(score, 6), "reasons": reasons, "route": route}


def _save_golden(fixture_name: str, artifact_name: str, data: dict[str, Any]) -> None:
    path = _golden_path(fixture_name, artifact_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n")


def _load_golden(fixture_name: str, artifact_name: str) -> dict[str, Any] | None:
    path = _golden_path(fixture_name, artifact_name)
    if not path.exists():
        return None
    return json.loads(path.read_bytes())


def _compare_golden(fixture_name: str, artifact_name: str, data: dict[str, Any]) -> bool:
    """Compare data to golden. Returns True if a new golden was generated."""
    golden = _load_golden(fixture_name, artifact_name)

    if golden is None or _REGENERATE:
        _save_golden(fixture_name, artifact_name, data)
        if golden is None:
            return True
        golden = data

    assert data == golden, f"Golden mismatch for {fixture_name}/{artifact_name}"
    return False


def _compare_confidence_golden(
    fixture_name: str,
    page_number: int,
    score: float,
    reasons: list[str],
    route: str,
) -> bool:
    """Compare confidence to golden. Returns True if a new golden was generated."""
    data = _serialize_confidence(score, reasons, route)
    golden = _load_golden(fixture_name, f"p{page_number:04d}_confidence")

    if golden is None or _REGENERATE:
        _save_golden(fixture_name, f"p{page_number:04d}_confidence", data)
        if golden is None:
            return True
        golden = data

    assert data["route"] == golden["route"], f"Route mismatch: {data['route']} != {golden['route']}"
    assert data["confidence"] == pytest.approx(golden["confidence"], abs=0.01), (
        f"Confidence mismatch: {data['confidence']} != {golden['confidence']}"
    )
    return False


# ---------------------------------------------------------------------------
# Save all golden artifacts for a fixture
# ---------------------------------------------------------------------------


def _save_all_goldens(fixture_name: str, result: EvidenceResult) -> None:
    """Save all golden artifacts for a fixture run."""
    generated = 0

    # Furniture profile
    if _compare_golden(
        fixture_name,
        "furniture_profile",
        _serialize_model(result.furniture_profile),
    ):
        generated += 1

    # Per-page artifacts
    for pn in sorted(result.region_graphs):
        if _compare_golden(
            fixture_name,
            f"p{pn:04d}_regions",
            _serialize_model(result.region_graphs[pn]),
        ):
            generated += 1
        if _compare_golden(
            fixture_name,
            f"p{pn:04d}_reading_order",
            _serialize_model(result.reading_orders[pn]),
        ):
            generated += 1
        if _compare_golden(
            fixture_name,
            f"p{pn:04d}_canonical",
            _serialize_model(result.canonicals[pn]),
        ):
            generated += 1

        score, reasons = result.confidences[pn]
        route = result.routes[pn]
        if _compare_confidence_golden(fixture_name, pn, score, reasons, route):
            generated += 1

    if generated > 0:
        pytest.skip(f"Generated {generated} golden(s) for {fixture_name} — rerun")


# ---------------------------------------------------------------------------
# Fixture 1: simple_semantic
# ---------------------------------------------------------------------------
# Single column, heading + body + 1 figure/caption, repeated header/footer
# across 2 pages. Low complexity → semantic route (>= 0.6).
# ---------------------------------------------------------------------------


def _build_simple_semantic() -> list[PrimitivePageEvidence]:
    pages: list[PrimitivePageEvidence] = []
    for pn in range(1, 3):
        texts = [
            # Repeated header
            text(0, pn, 0.05, 0.01, 0.95, 0.04, "Aeon Trespass: Odyssey — Core Rulebook"),
            # Repeated footer / page number
            text(1, pn, 0.45, 0.96, 0.55, 0.99, str(pn)),
            # Heading
            text(2, pn, 0.05, 0.08, 0.95, 0.12, f"Chapter {pn}: Introduction"),
            # Body paragraphs
            text(3, pn, 0.05, 0.14, 0.95, 0.20, f"Page {pn} body paragraph one."),
            text(4, pn, 0.05, 0.22, 0.95, 0.28, f"Page {pn} body paragraph two."),
            text(5, pn, 0.05, 0.30, 0.95, 0.36, f"Page {pn} body paragraph three."),
            # Figure caption
            text(6, pn, 0.15, 0.58, 0.85, 0.62, f"Figure {pn}.1: Diagram of the setup."),
        ]
        images_list = [
            # Single figure
            image(0, pn, 0.15, 0.40, 0.85, 0.56, content_hash=f"fig_{pn}_hash"),
        ]
        pages.append(page(pn, text_prims=texts, images=images_list))
    return pages


class TestSimpleSemantic:
    """Golden tests for a simple single-column layout → semantic route."""

    FIXTURE = "simple_semantic"

    def _run(self) -> EvidenceResult:
        return run_evidence_pipeline(_build_simple_semantic())

    def test_golden_artifacts(self) -> None:
        result = self._run()
        _save_all_goldens(self.FIXTURE, result)

    def test_routes_semantic(self) -> None:
        result = self._run()
        for pn, route in result.routes.items():
            assert route == "semantic", f"Page {pn} should route semantic, got {route}"

    def test_confidence_above_threshold(self) -> None:
        result = self._run()
        for pn, (score, _) in result.confidences.items():
            assert score >= 0.6, f"Page {pn} confidence {score:.3f} < 0.6"

    def test_furniture_detected(self) -> None:
        result = self._run()
        profile = result.furniture_profile
        assert len(profile.furniture_candidates) >= 2, "Expected header + page number furniture"
        types = {c.furniture_type for c in profile.furniture_candidates}
        assert "header" in types

    def test_has_figures(self) -> None:
        result = self._run()
        for pn, canonical in result.canonicals.items():
            assert canonical.has_figures, f"Page {pn} should have figures"
            assert not canonical.has_tables, f"Page {pn} should not have tables"
            assert not canonical.has_callouts, f"Page {pn} should not have callouts"

    def test_single_column(self) -> None:
        result = self._run()
        for pn, canonical in result.canonicals.items():
            assert canonical.estimated_column_count == 1, f"Page {pn} should have 1 column"


# ---------------------------------------------------------------------------
# Fixture 2: mixed_hard
# ---------------------------------------------------------------------------
# 2-column + callout + low-confidence table (2x1, text overlap) + figure
# across 4 pages. The degenerate table (few cells + text overlap) produces
# region confidence ~0.35, dragging the min down → hybrid route (0.3-0.6).
# ---------------------------------------------------------------------------


def _build_mixed_hard() -> list[PrimitivePageEvidence]:
    pages: list[PrimitivePageEvidence] = []
    for pn in range(1, 5):
        texts = [
            # Repeated header
            text(0, pn, 0.05, 0.01, 0.95, 0.04, "Aeon Trespass: Odyssey — Core Rulebook"),
            # Repeated footer
            text(1, pn, 0.45, 0.96, 0.55, 0.99, str(pn)),
            # Band 0: title
            text(2, pn, 0.05, 0.06, 0.95, 0.10, f"Section {pn}: Complex Layout"),
            # Band 1: two-column body (left)
            text(3, pn, 0.05, 0.14, 0.46, 0.18, f"Left column text page {pn}."),
            text(4, pn, 0.05, 0.19, 0.46, 0.23, f"Left column continued page {pn}."),
            # Band 1: two-column body (right)
            text(5, pn, 0.54, 0.14, 0.95, 0.18, f"Right column text page {pn}."),
            text(6, pn, 0.54, 0.19, 0.95, 0.23, f"Right column continued page {pn}."),
            # Band 2: callout text (inside drawing box)
            text(7, pn, 0.12, 0.30, 0.88, 0.34, "Important rules note!"),
            text(8, pn, 0.12, 0.35, 0.88, 0.39, "Read this carefully."),
            text(9, pn, 0.12, 0.40, 0.88, 0.44, "Third line of callout."),
            # Band 3: figure caption
            text(10, pn, 0.15, 0.62, 0.85, 0.66, f"Figure {pn}.1: Battle diagram."),
            # Band 4: text INSIDE the degenerate table bbox (triggers text overlap)
            text(11, pn, 0.12, 0.72, 0.88, 0.76, f"Table note A for page {pn}."),
            text(12, pn, 0.12, 0.77, 0.88, 0.81, f"Table note B for page {pn}."),
            # Band 5: body after table
            text(13, pn, 0.05, 0.88, 0.95, 0.92, f"Summary text for page {pn}."),
        ]
        images_list = [
            # Figure in band 3
            image(0, pn, 0.15, 0.48, 0.85, 0.60, content_hash=f"battle_{pn}_hash"),
        ]
        tables_list = [
            # Degenerate table: 2x1 (few cells) + text overlap → confidence ~0.35
            table(0, pn, 0.10, 0.70, 0.90, 0.84, rows=2, cols=1, strategy="stream"),
        ]
        drawings_list = [
            # Callout box enclosing texts 7, 8, 9
            drawing(0, pn, 0.10, 0.28, 0.90, 0.46),
        ]
        pages.append(
            page(
                pn,
                text_prims=texts,
                images=images_list,
                tables=tables_list,
                drawings=drawings_list,
            )
        )
    return pages


class TestMixedHard:
    """Golden tests for a multi-column page with tables/figures/callouts → hybrid route."""

    FIXTURE = "mixed_hard"

    def _run(self) -> EvidenceResult:
        return run_evidence_pipeline(_build_mixed_hard())

    def test_golden_artifacts(self) -> None:
        result = self._run()
        _save_all_goldens(self.FIXTURE, result)

    def test_routes_hybrid(self) -> None:
        result = self._run()
        for pn, route in result.routes.items():
            assert route == "hybrid", f"Page {pn} should route hybrid, got {route}"

    def test_confidence_in_hybrid_range(self) -> None:
        result = self._run()
        for pn, (score, _) in result.confidences.items():
            assert 0.3 <= score < 0.6, (
                f"Page {pn} confidence {score:.3f} not in hybrid range [0.3, 0.6)"
            )

    def test_has_all_entity_types(self) -> None:
        result = self._run()
        for pn, canonical in result.canonicals.items():
            assert canonical.has_tables, f"Page {pn} should have tables"
            assert canonical.has_figures, f"Page {pn} should have figures"
            assert canonical.has_callouts, f"Page {pn} should have callouts"

    def test_multi_column(self) -> None:
        result = self._run()
        for pn, canonical in result.canonicals.items():
            assert canonical.estimated_column_count >= 2, (
                f"Page {pn} should detect multi-column layout"
            )

    def test_furniture_detected(self) -> None:
        result = self._run()
        assert len(result.furniture_profile.furniture_candidates) >= 2


# ---------------------------------------------------------------------------
# Fixture 3: layout_extreme
# ---------------------------------------------------------------------------
# 2-column with sidebar + TWO degenerate tables (2x1, text overlap) +
# callouts + figure + high furniture fraction across 4 pages.
# Stacks every achievable penalty → facsimile route (< 0.3).
# ---------------------------------------------------------------------------


def _build_layout_extreme() -> list[PrimitivePageEvidence]:
    pages: list[PrimitivePageEvidence] = []
    for pn in range(1, 5):
        # Layout uses x range [0.16, 0.84] due to wide border panels.
        # Vertical bands separated by 3%+ gaps for clean band detection.
        texts = [
            # Repeated header text (furniture)
            text(0, pn, 0.16, 0.02, 0.84, 0.05, "Aeon Trespass: Odyssey — Core Rulebook"),
            # Repeated footer text (furniture)
            text(1, pn, 0.45, 0.95, 0.55, 0.98, str(pn)),
            # Band 0: full-width title  (y: 0.14-0.17)
            text(2, pn, 0.16, 0.14, 0.84, 0.17, f"Complex Section {pn}"),
            # Band 1: sidebar + main    (y: 0.22-0.30)
            text(3, pn, 0.16, 0.22, 0.30, 0.26, f"Sidebar note p{pn}"),
            text(4, pn, 0.16, 0.27, 0.30, 0.30, f"Sidebar extra p{pn}"),
            text(5, pn, 0.38, 0.22, 0.84, 0.26, f"Main body paragraph one p{pn}."),
            text(6, pn, 0.38, 0.27, 0.84, 0.30, f"Main body paragraph two p{pn}."),
            # Band 2: callout           (y: 0.35-0.50)
            text(7, pn, 0.18, 0.36, 0.82, 0.40, "Warning: critical rules!"),
            text(8, pn, 0.18, 0.41, 0.82, 0.45, "Read this section carefully."),
            text(9, pn, 0.18, 0.46, 0.82, 0.50, "Third line of callout."),
            # Band 3: degenerate table 1 + text overlap (y: 0.55-0.65)
            text(10, pn, 0.18, 0.56, 0.82, 0.60, f"Table note A for page {pn}."),
            text(11, pn, 0.18, 0.61, 0.82, 0.64, f"Table note B for page {pn}."),
            # Band 4: figure + caption  (y: 0.69-0.76)
            text(12, pn, 0.20, 0.73, 0.80, 0.76, f"Figure {pn}.1: Complex diagram."),
            # Band 5: degenerate table 2 + text overlap (y: 0.82-0.90)
            text(13, pn, 0.18, 0.83, 0.82, 0.86, f"Stats note A for page {pn}."),
            text(14, pn, 0.18, 0.87, 0.82, 0.89, f"Stats note B for page {pn}."),
        ]
        images_list = [
            # Figure (y: 0.69-0.76)
            image(0, pn, 0.16, 0.69, 0.84, 0.76, content_hash=f"extreme_{pn}_hash"),
            # Large repeated border panels → high furniture fraction
            image(1, pn, 0.00, 0.00, 0.15, 1.00, content_hash="border_left"),
            image(2, pn, 0.85, 0.00, 1.00, 1.00, content_hash="border_right"),
            # Large repeated header/footer panels
            image(3, pn, 0.00, 0.00, 1.00, 0.13, content_hash="header_panel"),
            image(4, pn, 0.00, 0.92, 1.00, 1.00, content_hash="footer_panel"),
        ]
        tables_list = [
            # Degenerate table 1: 2x1 + text overlap → confidence ~0.35
            table(0, pn, 0.16, 0.55, 0.84, 0.65, rows=2, cols=1, strategy="stream"),
            # Degenerate table 2: 2x1 + text overlap → confidence ~0.35
            table(1, pn, 0.16, 0.83, 0.84, 0.90, rows=2, cols=1, strategy="stream"),
        ]
        drawings_list = [
            # Callout box enclosing texts 7, 8, 9
            drawing(0, pn, 0.16, 0.35, 0.84, 0.51),
        ]
        pages.append(
            page(
                pn,
                text_prims=texts,
                images=images_list,
                tables=tables_list,
                drawings=drawings_list,
            )
        )
    return pages


class TestLayoutExtreme:
    """Golden tests for an extreme layout with all penalties stacked."""

    FIXTURE = "layout_extreme"

    def _run(self) -> EvidenceResult:
        return run_evidence_pipeline(_build_layout_extreme())

    def test_golden_artifacts(self) -> None:
        result = self._run()
        _save_all_goldens(self.FIXTURE, result)

    def test_routes_not_semantic(self) -> None:
        result = self._run()
        for pn, route in result.routes.items():
            assert route != "semantic", (
                f"Page {pn} should NOT route semantic (got confidence "
                f"{result.confidences[pn][0]:.3f})"
            )

    def test_confidence_below_semantic_threshold(self) -> None:
        result = self._run()
        for pn, (score, _) in result.confidences.items():
            assert score < 0.6, f"Page {pn} confidence {score:.3f} should be < 0.6"

    def test_all_entity_types_present(self) -> None:
        result = self._run()
        for pn, canonical in result.canonicals.items():
            assert canonical.has_tables, f"Page {pn} should have tables"
            assert canonical.has_figures, f"Page {pn} should have figures"
            assert canonical.has_callouts, f"Page {pn} should have callouts"

    def test_lower_confidence_than_mixed(self) -> None:
        """Extreme layout should have lower confidence than mixed_hard."""
        mixed = run_evidence_pipeline(_build_mixed_hard())
        extreme = self._run()
        avg_mixed = sum(s for s, _ in mixed.confidences.values()) / len(mixed.confidences)
        avg_extreme = sum(s for s, _ in extreme.confidences.values()) / len(extreme.confidences)
        assert avg_extreme < avg_mixed, (
            f"Extreme ({avg_extreme:.3f}) should have lower confidence than mixed ({avg_mixed:.3f})"
        )

    def test_furniture_detected(self) -> None:
        result = self._run()
        assert len(result.furniture_profile.furniture_candidates) >= 2


# ---------------------------------------------------------------------------
# Cross-fixture parametrized invariant tests
# ---------------------------------------------------------------------------

_ALL_FIXTURES = [
    ("simple_semantic", _build_simple_semantic),
    ("mixed_hard", _build_mixed_hard),
    ("layout_extreme", _build_layout_extreme),
]


class TestEvidenceInvariants:
    """Invariants that must hold for any evidence pipeline output."""

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_confidence_bounded(self, name: str, builder: Any) -> None:
        result = run_evidence_pipeline(builder())
        for pn, (score, _) in result.confidences.items():
            assert 0.0 <= score <= 1.0, f"{name} page {pn}: confidence {score} out of [0, 1]"

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_route_matches_confidence(self, name: str, builder: Any) -> None:
        result = run_evidence_pipeline(builder())
        for pn in result.routes:
            score = result.confidences[pn][0]
            route = result.routes[pn]
            if score >= 0.6:
                assert route == "semantic", f"{name} p{pn}: {score:.3f} → {route}"
            elif score >= 0.3:
                assert route == "hybrid", f"{name} p{pn}: {score:.3f} → {route}"
            else:
                assert route == "facsimile", f"{name} p{pn}: {score:.3f} → {route}"

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_deterministic(self, name: str, builder: Any) -> None:
        """Running the pipeline twice produces identical results."""
        pages = builder()
        r1 = run_evidence_pipeline(pages)
        r2 = run_evidence_pipeline(pages)
        for pn in r1.confidences:
            assert r1.confidences[pn] == r2.confidences[pn], (
                f"{name} p{pn}: non-deterministic confidence"
            )
            assert r1.routes[pn] == r2.routes[pn], f"{name} p{pn}: non-deterministic route"

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_region_ids_unique(self, name: str, builder: Any) -> None:
        result = run_evidence_pipeline(builder())
        for pn, graph in result.region_graphs.items():
            ids = [r.region_id for r in graph.regions]
            assert len(ids) == len(set(ids)), f"{name} p{pn}: duplicate region IDs"

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_reading_order_contiguous(self, name: str, builder: Any) -> None:
        result = run_evidence_pipeline(builder())
        for pn, order in result.reading_orders.items():
            indices = [e.sequence_index for e in order.entries]
            assert indices == list(range(len(indices))), (
                f"{name} p{pn}: reading order not contiguous"
            )

    @pytest.mark.parametrize(
        ("name", "builder"),
        _ALL_FIXTURES,
        ids=[f[0] for f in _ALL_FIXTURES],
    )
    def test_canonical_has_region_graph(self, name: str, builder: Any) -> None:
        result = run_evidence_pipeline(builder())
        for pn, canonical in result.canonicals.items():
            assert canonical.region_graph is not None, (
                f"{name} p{pn}: canonical missing region_graph"
            )
            assert canonical.reading_order is not None, (
                f"{name} p{pn}: canonical missing reading_order"
            )
