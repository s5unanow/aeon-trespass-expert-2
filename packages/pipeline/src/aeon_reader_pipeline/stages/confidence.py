"""Page confidence scoring and deterministic fallback-routing policy.

Derives a structured confidence score from CanonicalPageEvidence signals
(region quality, reading-order quality, layout complexity, entity density)
and maps the score to a render mode via fixed thresholds.

Introduced by S5U-263.
"""

from __future__ import annotations

from typing import Literal

from aeon_reader_pipeline.models.evidence_models import CanonicalPageEvidence

# ---------------------------------------------------------------------------
# Routing thresholds
# ---------------------------------------------------------------------------

SEMANTIC_THRESHOLD = 0.6
"""Pages at or above this confidence stay fully semantic."""

HYBRID_THRESHOLD = 0.3
"""Pages between HYBRID_THRESHOLD and SEMANTIC_THRESHOLD get hybrid rendering."""

# Below HYBRID_THRESHOLD → facsimile.

# ---------------------------------------------------------------------------
# Signal weights (sum to ~1.0 for interpretability)
# ---------------------------------------------------------------------------

_W_REGION_CONFIDENCE = 0.25
_W_ORDER_CONFIDENCE = 0.25
_W_UNASSIGNED_REGIONS = 0.15
_W_COLUMN_COMPLEXITY = 0.15
_W_ENTITY_DENSITY = 0.10
_W_FURNITURE = 0.10


def score_page_confidence(
    canonical: CanonicalPageEvidence,
) -> tuple[float, list[str]]:
    """Score page confidence from canonical evidence signals.

    Returns ``(confidence, reasons)`` where *confidence* is in [0, 1] and
    *reasons* lists human-readable explanations for each penalty applied.
    """
    score = 1.0
    reasons: list[str] = []

    # --- Signal 1: minimum region confidence ----------------------------------
    region_min = _min_region_confidence(canonical)
    if region_min < 1.0:
        penalty = (1.0 - region_min) * _W_REGION_CONFIDENCE
        score -= penalty
        reasons.append(f"region_confidence_min={region_min:.2f} (penalty={penalty:.3f})")

    # --- Signal 2: minimum reading-order confidence ---------------------------
    order_min = _min_reading_order_confidence(canonical)
    if order_min < 1.0:
        penalty = (1.0 - order_min) * _W_ORDER_CONFIDENCE
        score -= penalty
        reasons.append(f"reading_order_confidence_min={order_min:.2f} (penalty={penalty:.3f})")

    # --- Signal 3: unassigned region fraction ---------------------------------
    unassigned_frac = _unassigned_region_fraction(canonical)
    if unassigned_frac > 0.0:
        penalty = unassigned_frac * _W_UNASSIGNED_REGIONS
        score -= penalty
        reasons.append(f"unassigned_region_fraction={unassigned_frac:.2f} (penalty={penalty:.3f})")

    # --- Signal 4: column complexity ------------------------------------------
    col_penalty = _column_complexity_penalty(canonical)
    if col_penalty > 0.0:
        weighted = col_penalty * _W_COLUMN_COMPLEXITY
        score -= weighted
        reasons.append(f"column_count={canonical.estimated_column_count} (penalty={weighted:.3f})")

    # --- Signal 5: entity density ---------------------------------------------
    entity_penalty = _entity_density_penalty(canonical)
    if entity_penalty > 0.0:
        weighted = entity_penalty * _W_ENTITY_DENSITY
        score -= weighted
        reasons.append(f"entity_density_penalty={entity_penalty:.2f} (penalty={weighted:.3f})")

    # --- Signal 6: furniture fraction -----------------------------------------
    if canonical.furniture_fraction > 0.5:
        excess = canonical.furniture_fraction - 0.5
        penalty = min(excess * 2.0, 1.0) * _W_FURNITURE
        score -= penalty
        reasons.append(
            f"furniture_fraction={canonical.furniture_fraction:.2f} (penalty={penalty:.3f})"
        )

    score = max(0.0, min(1.0, score))
    return score, reasons


def route_page(
    confidence: float,
) -> Literal["semantic", "hybrid", "facsimile"]:
    """Map a confidence score to a deterministic render mode.

    Thresholds:
        confidence >= 0.6  → semantic
        confidence >= 0.3  → hybrid (semantic blocks + fallback image)
        confidence <  0.3  → facsimile (image-only)
    """
    if confidence >= SEMANTIC_THRESHOLD:
        return "semantic"
    if confidence >= HYBRID_THRESHOLD:
        return "hybrid"
    return "facsimile"


# ---------------------------------------------------------------------------
# Signal extraction helpers
# ---------------------------------------------------------------------------


def _min_region_confidence(canonical: CanonicalPageEvidence) -> float:
    """Minimum confidence across all regions in the graph.

    Returns 1.0 if no region graph or no regions (no penalty).
    """
    rg = canonical.region_graph
    if rg is None or not rg.regions:
        return 1.0
    return min(r.confidence.value for r in rg.regions)


def _min_reading_order_confidence(canonical: CanonicalPageEvidence) -> float:
    """Minimum confidence across reading-order entries.

    Returns 1.0 if no reading order or no entries (no penalty).
    """
    ro = canonical.reading_order
    if ro is None or not ro.entries:
        return 1.0
    return min(e.confidence.value for e in ro.entries)


def _unassigned_region_fraction(canonical: CanonicalPageEvidence) -> float:
    """Fraction of regions not assigned to the reading order.

    Returns 0.0 if no reading order or no regions.
    """
    ro = canonical.reading_order
    if ro is None or ro.total_regions == 0:
        return 0.0
    return len(ro.unassigned_region_ids) / ro.total_regions


def _column_complexity_penalty(canonical: CanonicalPageEvidence) -> float:
    """Penalty for multi-column layouts.

    Single column → 0.0, two columns → 0.3, three+ → 0.6.
    """
    cols = canonical.estimated_column_count
    if cols <= 1:
        return 0.0
    if cols == 2:
        return 0.3
    return 0.6


def _entity_density_penalty(canonical: CanonicalPageEvidence) -> float:
    """Penalty based on the number of complex entity types present.

    Each entity type (tables, figures, callouts) adds 0.2 penalty.
    """
    count = sum([canonical.has_tables, canonical.has_figures, canonical.has_callouts])
    return count * 0.2
