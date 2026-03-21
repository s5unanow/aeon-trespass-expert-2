"""Tests for the ExtractedPage → PrimitivePageEvidence converter."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_builder import build_primitive_evidence
from aeon_reader_pipeline.models.extract_models import (
    BBox,
    ExtractedPage,
    FontInfo,
    RawImageInfo,
    RawTableCell,
    RawTableInfo,
    TextBlock,
    TextLine,
    TextSpan,
)


def _make_extracted_page(
    *,
    page_number: int = 1,
    doc_id: str = "test-doc",
    width_pt: float = 612.0,
    height_pt: float = 792.0,
) -> ExtractedPage:
    """Build a realistic ExtractedPage fixture."""
    return ExtractedPage(
        page_number=page_number,
        width_pt=width_pt,
        height_pt=height_pt,
        rotation=0,
        text_blocks=[
            TextBlock(
                block_index=0,
                lines=[
                    TextLine(
                        spans=[
                            TextSpan(
                                text="Chapter 1: Setup",
                                font=FontInfo(name="Arial-Bold", size=18.0, is_bold=True),
                                bbox=BBox(x0=72, y0=72, x1=300, y1=92),
                            )
                        ],
                        bbox=BBox(x0=72, y0=72, x1=300, y1=92),
                    )
                ],
                bbox=BBox(x0=72, y0=72, x1=300, y1=92),
            ),
            TextBlock(
                block_index=1,
                lines=[
                    TextLine(
                        spans=[
                            TextSpan(
                                text="Body text paragraph.",
                                font=FontInfo(name="Arial", size=11.0),
                                bbox=BBox(x0=72, y0=110, x1=500, y1=124),
                            )
                        ],
                        bbox=BBox(x0=72, y0=110, x1=500, y1=124),
                    )
                ],
                bbox=BBox(x0=72, y0=110, x1=500, y1=124),
            ),
        ],
        images=[
            RawImageInfo(
                image_index=0,
                xref=42,
                width=640,
                height=480,
                colorspace="RGB",
                bpc=8,
                bbox=BBox(x0=72, y0=200, x1=540, y1=500),
                content_hash="abc123def456",
                stored_as="abc123def456.png",
            ),
        ],
        tables=[
            RawTableInfo(
                table_index=0,
                rows=2,
                cols=3,
                bbox=BBox(x0=72, y0=550, x1=540, y1=700),
                cells=[
                    RawTableCell(row=0, col=0, text="A"),
                    RawTableCell(row=0, col=1, text="B"),
                    RawTableCell(row=0, col=2, text="C"),
                    RawTableCell(row=1, col=0, text="1"),
                    RawTableCell(row=1, col=1, text="2"),
                    RawTableCell(row=1, col=2, text="3"),
                ],
            ),
        ],
        fonts_used=["Arial-Bold", "Arial"],
        char_count=37,
        source_pdf_sha256="deadbeef" * 8,
        doc_id=doc_id,
    )


class TestBuildPrimitiveEvidence:
    def test_page_metadata_carried(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        assert evidence.page_number == 1
        assert evidence.doc_id == "test-doc"
        assert evidence.width_pt == 612.0
        assert evidence.height_pt == 792.0
        assert evidence.rotation == 0
        assert evidence.source_pdf_sha256 == "deadbeef" * 8
        assert evidence.char_count == 37

    def test_extraction_method_is_pymupdf(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)
        assert evidence.extraction_method == "pymupdf"

    def test_text_primitives_converted(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        assert len(evidence.text_primitives) == 2

        tp0 = evidence.text_primitives[0]
        assert tp0.primitive_id == "text:p0001:000"
        assert tp0.text == "Chapter 1: Setup"
        assert tp0.line_count == 1
        assert tp0.font_name == "Arial-Bold"
        assert tp0.font_size == 18.0
        assert tp0.is_bold is True
        # Normalized coords: 72/612 ≈ 0.1176, 72/792 ≈ 0.0909
        assert 0.0 < tp0.bbox_norm.x0 < 1.0
        assert 0.0 < tp0.bbox_norm.y0 < 1.0

        tp1 = evidence.text_primitives[1]
        assert tp1.primitive_id == "text:p0001:001"
        assert tp1.font_name == "Arial"
        assert tp1.is_bold is False

    def test_image_primitives_converted(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        assert len(evidence.image_primitives) == 1
        ip = evidence.image_primitives[0]
        assert ip.primitive_id == "image:p0001:000"
        assert ip.content_hash == "abc123def456"
        assert ip.width_px == 640
        assert ip.height_px == 480
        assert ip.colorspace == "RGB"
        assert 0.0 < ip.bbox_norm.x0 < 1.0

    def test_table_primitives_converted(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        assert len(evidence.table_primitives) == 1
        tp = evidence.table_primitives[0]
        assert tp.primitive_id == "table:p0001:000"
        assert tp.rows == 2
        assert tp.cols == 3
        assert tp.cell_count == 6
        assert tp.extraction_strategy == "default"
        assert tp.area_fraction > 0.0

    def test_table_strategy_propagated(self) -> None:
        page = _make_extracted_page()
        page.tables[0].extraction_strategy = "lines_strict"
        evidence = build_primitive_evidence(page)

        tp = evidence.table_primitives[0]
        assert tp.extraction_strategy == "lines_strict"

    def test_font_summary_computed(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        fs = evidence.font_summary
        assert fs.unique_font_count == 2
        # Body text has more chars, so Arial should dominate
        assert fs.dominant_font == "Arial"
        assert fs.dominant_size == 11.0

    def test_raster_handle_attached(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        rh = evidence.raster_handle
        assert rh is not None
        assert rh.source_pdf_sha256 == "deadbeef" * 8
        assert rh.page_number == 1
        assert rh.width_pt == 612.0
        assert rh.height_pt == 792.0
        assert rh.raster_path is None
        assert rh.default_dpi == 150

    def test_empty_page(self) -> None:
        page = ExtractedPage(
            page_number=5,
            width_pt=612.0,
            height_pt=792.0,
            doc_id="empty-doc",
        )
        evidence = build_primitive_evidence(page)

        assert evidence.page_number == 5
        assert evidence.text_primitives == []
        assert evidence.image_primitives == []
        assert evidence.table_primitives == []
        assert evidence.font_summary.dominant_font == ""
        assert evidence.font_summary.unique_font_count == 0
        assert evidence.raster_handle is not None

    def test_json_roundtrip(self) -> None:
        page = _make_extracted_page()
        evidence = build_primitive_evidence(page)

        data = evidence.model_dump(mode="json")
        from aeon_reader_pipeline.models.evidence_models import PrimitivePageEvidence

        restored = PrimitivePageEvidence.model_validate(data)

        assert restored.page_number == evidence.page_number
        assert len(restored.text_primitives) == len(evidence.text_primitives)
        assert len(restored.image_primitives) == len(evidence.image_primitives)
        assert len(restored.table_primitives) == len(evidence.table_primitives)
        assert restored.raster_handle is not None
        assert restored.raster_handle.page_number == 1

    def test_different_page_numbers(self) -> None:
        page = _make_extracted_page(page_number=42)
        evidence = build_primitive_evidence(page)

        assert evidence.text_primitives[0].primitive_id == "text:p0042:000"
        assert evidence.image_primitives[0].primitive_id == "image:p0042:000"
        assert evidence.table_primitives[0].primitive_id == "table:p0042:000"
        assert evidence.raster_handle is not None
        assert evidence.raster_handle.page_number == 42
