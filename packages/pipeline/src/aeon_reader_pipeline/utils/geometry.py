"""Coordinate normalization utilities for PDF extraction."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import NormalizedBBox
from aeon_reader_pipeline.models.extract_models import BBox


def normalize_bbox(bbox: BBox, width_pt: float, height_pt: float) -> NormalizedBBox:
    """Convert a PDF-point bounding box to normalized [0, 1] page-space.

    Values are clamped to [0, 1] to handle minor extraction overflows.
    Raises ValueError if page dimensions are not positive.
    """
    if width_pt <= 0 or height_pt <= 0:
        raise ValueError(f"Page dimensions must be positive, got {width_pt}x{height_pt}")

    return NormalizedBBox(
        x0=_clamp(bbox.x0 / width_pt),
        y0=_clamp(bbox.y0 / height_pt),
        x1=_clamp(bbox.x1 / width_pt),
        y1=_clamp(bbox.y1 / height_pt),
    )


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))
