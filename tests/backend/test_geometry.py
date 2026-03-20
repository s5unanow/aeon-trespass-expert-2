"""Tests for coordinate normalization utilities."""

from __future__ import annotations

import pytest

from aeon_reader_pipeline.models.evidence_models import NormalizedBBox
from aeon_reader_pipeline.models.extract_models import BBox
from aeon_reader_pipeline.utils.geometry import normalize_bbox


class TestNormalizeBBox:
    def test_full_page(self) -> None:
        bbox = BBox(x0=0, y0=0, x1=612, y1=792)
        result = normalize_bbox(bbox, 612, 792)
        assert result == NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)

    def test_centered_box(self) -> None:
        bbox = BBox(x0=153, y0=198, x1=459, y1=594)
        result = normalize_bbox(bbox, 612, 792)
        assert result.x0 == pytest.approx(0.25, abs=0.001)
        assert result.y0 == pytest.approx(0.25, abs=0.001)
        assert result.x1 == pytest.approx(0.75, abs=0.001)
        assert result.y1 == pytest.approx(0.75, abs=0.001)

    def test_clamps_overflow(self) -> None:
        bbox = BBox(x0=-5, y0=-2, x1=620, y1=800)
        result = normalize_bbox(bbox, 612, 792)
        assert result.x0 == 0.0
        assert result.y0 == 0.0
        assert result.x1 == 1.0
        assert result.y1 == 1.0

    def test_zero_origin(self) -> None:
        bbox = BBox(x0=0, y0=0, x1=0, y1=0)
        result = normalize_bbox(bbox, 612, 792)
        assert result == NormalizedBBox(x0=0.0, y0=0.0, x1=0.0, y1=0.0)

    def test_rejects_zero_width(self) -> None:
        bbox = BBox(x0=10, y0=10, x1=100, y1=100)
        with pytest.raises(ValueError, match="positive"):
            normalize_bbox(bbox, 0, 792)

    def test_rejects_zero_height(self) -> None:
        bbox = BBox(x0=10, y0=10, x1=100, y1=100)
        with pytest.raises(ValueError, match="positive"):
            normalize_bbox(bbox, 612, 0)

    def test_rejects_negative_dimensions(self) -> None:
        bbox = BBox(x0=10, y0=10, x1=100, y1=100)
        with pytest.raises(ValueError, match="positive"):
            normalize_bbox(bbox, -612, 792)

    def test_non_standard_page_size(self) -> None:
        bbox = BBox(x0=50, y0=100, x1=150, y1=200)
        result = normalize_bbox(bbox, 200, 400)
        assert result.x0 == pytest.approx(0.25)
        assert result.y0 == pytest.approx(0.25)
        assert result.x1 == pytest.approx(0.75)
        assert result.y1 == pytest.approx(0.5)
