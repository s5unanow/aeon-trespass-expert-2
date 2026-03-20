"""Tests for cross-page furniture detection and page-template classification."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.furniture_detection import (
    compute_page_furniture,
    detect_furniture,
)


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _make_page(
    page_number: int,
    *,
    doc_id: str = "test-doc",
    text_primitives: list[TextPrimitiveEvidence] | None = None,
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id=doc_id,
        width_pt=612.0,
        height_pt=792.0,
        text_primitives=text_primitives or [],
        image_primitives=image_primitives or [],
        drawing_primitives=drawing_primitives or [],
    )


def _header_text(page_number: int) -> TextPrimitiveEvidence:
    """A header-like text primitive at the top of the page."""
    return TextPrimitiveEvidence(
        primitive_id=f"text:p{page_number:04d}:000",
        bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
        text="Aeon Trespass: Odyssey — Rules Reference",
        font_name="Helvetica-Bold",
        font_size=9.0,
        is_bold=True,
    )


def _footer_text(page_number: int) -> TextPrimitiveEvidence:
    """A footer-like text primitive at the bottom of the page."""
    return TextPrimitiveEvidence(
        primitive_id=f"text:p{page_number:04d}:099",
        bbox_norm=_bbox(0.1, 0.96, 0.9, 0.99),
        text="www.intothevoid.eu",
        font_name="Helvetica",
        font_size=7.0,
    )


def _page_number_text(page_number: int) -> TextPrimitiveEvidence:
    """A page-number text primitive at the bottom center."""
    return TextPrimitiveEvidence(
        primitive_id=f"text:p{page_number:04d}:098",
        bbox_norm=_bbox(0.47, 0.96, 0.53, 0.99),
        text=str(page_number),
        font_name="Helvetica",
        font_size=9.0,
    )


def _body_text(page_number: int, index: int = 1) -> TextPrimitiveEvidence:
    """A body-text primitive in the middle of the page."""
    return TextPrimitiveEvidence(
        primitive_id=f"text:p{page_number:04d}:{index:03d}",
        bbox_norm=_bbox(0.1, 0.15, 0.9, 0.30),
        text=f"Body paragraph content on page {page_number}.",
        font_name="Helvetica",
        font_size=11.0,
    )


class TestSinglePageDocument:
    def test_returns_empty_profile(self) -> None:
        """A single-page document cannot have repeated elements."""
        pages = [_make_page(1, text_primitives=[_header_text(1), _body_text(1)])]
        profile = detect_furniture(pages)
        assert profile.total_pages_analyzed == 1
        assert profile.furniture_candidates == []
        assert profile.templates == []

    def test_empty_input_returns_empty(self) -> None:
        profile = detect_furniture([])
        assert profile.total_pages_analyzed == 0
        assert profile.furniture_candidates == []


class TestRepeatedHeaderDetected:
    def test_header_on_all_pages(self) -> None:
        """A text element at the top of every page is detected as header."""
        pages = [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i)],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        assert len(profile.furniture_candidates) == 1
        cand = profile.furniture_candidates[0]
        assert cand.furniture_type == "header"
        assert cand.repetition_rate == 1.0
        assert cand.page_numbers == [1, 2, 3, 4, 5]
        assert cand.text_sample.startswith("Aeon Trespass")

    def test_header_on_most_pages(self) -> None:
        """Header on 4/5 pages still detected (80% > 50% threshold)."""
        pages = [
            _make_page(i, text_primitives=[_header_text(i), _body_text(i)]) for i in range(1, 5)
        ] + [_make_page(5, text_primitives=[_body_text(5)])]
        profile = detect_furniture(pages)
        headers = [c for c in profile.furniture_candidates if c.furniture_type == "header"]
        assert len(headers) == 1
        assert headers[0].repetition_rate == 0.8


class TestRepeatedFooterDetected:
    def test_footer_on_all_pages(self) -> None:
        pages = [
            _make_page(i, text_primitives=[_body_text(i), _footer_text(i)]) for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        footers = [c for c in profile.furniture_candidates if c.furniture_type == "footer"]
        assert len(footers) == 1
        assert footers[0].repetition_rate == 1.0


class TestPageNumberDetected:
    def test_page_numbers_detected(self) -> None:
        """Page numbers with varying text but same position/font are detected."""
        pages = [
            _make_page(
                i,
                text_primitives=[_body_text(i), _page_number_text(i)],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        pn_cands = [c for c in profile.furniture_candidates if c.furniture_type == "page_number"]
        assert len(pn_cands) == 1
        assert pn_cands[0].page_numbers == [1, 2, 3, 4, 5]


class TestDecorativeDrawingAsBorder:
    def test_repeated_decorative_drawing(self) -> None:
        """A decorative drawing spanning most of the page is detected as border."""
        pages = [
            _make_page(
                i,
                text_primitives=[_body_text(i)],
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id=f"drawing:p{i:04d}:000",
                        bbox_norm=_bbox(0.0, 0.0, 1.0, 1.0),
                        path_count=20,
                        is_decorative=True,
                    )
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        borders = [c for c in profile.furniture_candidates if c.furniture_type == "border"]
        assert len(borders) == 1
        assert borders[0].repetition_rate == 1.0

    def test_small_decorative_drawing_as_ornament(self) -> None:
        """A small decorative drawing is classified as ornament."""
        pages = [
            _make_page(
                i,
                text_primitives=[_body_text(i)],
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id=f"drawing:p{i:04d}:000",
                        bbox_norm=_bbox(0.45, 0.01, 0.55, 0.04),
                        path_count=3,
                        is_decorative=True,
                    )
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        ornaments = [c for c in profile.furniture_candidates if c.furniture_type == "ornament"]
        assert len(ornaments) == 1


class TestDividerDetected:
    def test_thin_wide_non_decorative_drawing_as_divider(self) -> None:
        """A thin wide non-decorative drawing at the edge is a divider."""
        pages = [
            _make_page(
                i,
                text_primitives=[_body_text(i)],
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id=f"drawing:p{i:04d}:000",
                        bbox_norm=_bbox(0.05, 0.01, 0.95, 0.02),
                        path_count=2,
                        is_decorative=False,
                    )
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        dividers = [c for c in profile.furniture_candidates if c.furniture_type == "divider"]
        assert len(dividers) == 1


class TestNonRepeatedNotFurniture:
    def test_element_on_one_page_excluded(self) -> None:
        """An element appearing on only 1 of 5 pages is not furniture."""
        pages = [_make_page(i, text_primitives=[_body_text(i)]) for i in range(1, 6)]
        # Add a unique header only on page 1
        pages[0] = _make_page(
            1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
                    text="Unique Chapter Opener",
                    font_name="Helvetica-Bold",
                    font_size=9.0,
                    is_bold=True,
                ),
                _body_text(1),
            ],
        )
        profile = detect_furniture(pages)
        assert profile.furniture_candidates == []


class TestBodyTextNotFurniture:
    def test_center_text_not_classified(self) -> None:
        """Repeated body-zone text at the center of the page is not furniture."""
        # Same text, same font, same position in the center of every page
        pages = [
            _make_page(
                i,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id=f"text:p{i:04d}:001",
                        bbox_norm=_bbox(0.1, 0.40, 0.9, 0.60),
                        text="Repeated body content",
                        font_name="Helvetica",
                        font_size=11.0,
                    ),
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        # Center zone text should not pass the edge-placement gate
        assert profile.furniture_candidates == []


class TestTemplateAssignment:
    def test_pages_with_same_furniture_share_template(self) -> None:
        """Pages sharing the same furniture set get the same template_id."""
        pages = [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i), _footer_text(i)],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        assert len(profile.templates) == 1
        assert profile.templates[0].page_numbers == [1, 2, 3, 4, 5]
        assert len(profile.templates[0].furniture_ids) >= 2  # header + footer

    def test_pages_with_different_furniture_get_different_templates(self) -> None:
        """Pages with different furniture patterns get different template_ids."""
        # Pages 1-3: header + footer; Pages 4-5: header only
        pages = [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i), _footer_text(i)],
            )
            for i in range(1, 4)
        ] + [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i)],
            )
            for i in range(4, 6)
        ]
        profile = detect_furniture(pages, min_repetition_rate=0.4)
        # With 0.4 threshold: header on 5/5 (1.0), footer on 3/5 (0.6) both qualify
        assert len(profile.templates) == 2
        tpl_page_sets = [set(t.page_numbers) for t in profile.templates]
        assert {1, 2, 3} in tpl_page_sets
        assert {4, 5} in tpl_page_sets


class TestFurnitureFraction:
    def test_fraction_from_bbox_area(self) -> None:
        """Furniture fraction is computed from total furniture bbox area."""
        pages = [
            _make_page(
                i,
                text_primitives=[
                    # Header spanning 80% width, 3% height → area = 0.8 * 0.03 = 0.024
                    TextPrimitiveEvidence(
                        primitive_id=f"text:p{i:04d}:000",
                        bbox_norm=_bbox(0.1, 0.02, 0.9, 0.05),
                        text="Header",
                        font_name="Helvetica",
                        font_size=9.0,
                    ),
                    _body_text(i),
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        _ids, _tpls, fractions = compute_page_furniture(profile)
        # All pages should have the same fraction
        for pn in range(1, 6):
            assert fractions[pn] > 0.0
            assert fractions[pn] < 0.1  # Header area is small


class TestMinRepetitionRate:
    def test_higher_threshold_excludes_candidates(self) -> None:
        """A higher min_repetition_rate excludes candidates appearing on fewer pages."""
        # Header on 3/5 pages = 60% repetition rate
        pages = [
            _make_page(i, text_primitives=[_header_text(i), _body_text(i)]) for i in range(1, 4)
        ] + [_make_page(i, text_primitives=[_body_text(i)]) for i in range(4, 6)]

        # 50% threshold: header qualifies (60% > 50%)
        profile_low = detect_furniture(pages, min_repetition_rate=0.5)
        assert len(profile_low.furniture_candidates) == 1

        # 80% threshold: header excluded (60% < 80%)
        profile_high = detect_furniture(pages, min_repetition_rate=0.8)
        assert len(profile_high.furniture_candidates) == 0


class TestRepeatedImageAsFurniture:
    def test_repeated_edge_image(self) -> None:
        """A repeated image at a page edge is detected as furniture."""
        pages = [
            _make_page(
                i,
                text_primitives=[_body_text(i)],
                image_primitives=[
                    ImagePrimitiveEvidence(
                        primitive_id=f"image:p{i:04d}:000",
                        bbox_norm=_bbox(0.0, 0.0, 0.15, 0.06),
                        content_hash="sha256:logo_hash",
                        width_px=100,
                        height_px=40,
                    )
                ],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        assert len(profile.furniture_candidates) == 1
        assert profile.furniture_candidates[0].source_primitive_kind == "image"


class TestComputePageFurniture:
    def test_lookups_populated(self) -> None:
        """compute_page_furniture returns correct per-page lookups."""
        pages = [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i), _page_number_text(i)],
            )
            for i in range(1, 4)
        ]
        profile = detect_furniture(pages)
        furn_ids, tpl_ids, fractions = compute_page_furniture(profile)

        for pn in range(1, 4):
            assert pn in furn_ids
            assert len(furn_ids[pn]) >= 1
            assert pn in tpl_ids
            assert tpl_ids[pn].startswith("tpl:")
            assert pn in fractions
            assert 0.0 < fractions[pn] < 1.0


class TestDocumentFurnitureProfileRoundTrip:
    def test_json_roundtrip(self) -> None:
        """DocumentFurnitureProfile survives JSON serialization round-trip."""
        pages = [
            _make_page(
                i,
                text_primitives=[_header_text(i), _body_text(i), _footer_text(i)],
            )
            for i in range(1, 6)
        ]
        profile = detect_furniture(pages)
        payload = profile.model_dump(mode="json")
        restored = DocumentFurnitureProfile.model_validate(payload)
        assert restored == profile
