"""Build PrimitivePageEvidence from ExtractedPage.

Converts raw extraction artifacts into the provenance-tagged evidence layer
with normalized coordinates, stable primitive IDs, and a raster handle.
"""

from __future__ import annotations

from collections import Counter

from aeon_reader_pipeline.models.evidence_models import (
    FontSummary,
    ImagePrimitiveEvidence,
    PageRasterHandle,
    PrimitivePageEvidence,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.models.extract_models import (
    ExtractedPage,
    RawImageInfo,
    RawTableInfo,
    TextBlock,
)
from aeon_reader_pipeline.utils.geometry import normalize_bbox
from aeon_reader_pipeline.utils.ids import primitive_id


def build_primitive_evidence(page: ExtractedPage) -> PrimitivePageEvidence:
    """Convert an ExtractedPage into PrimitivePageEvidence.

    Assigns stable provenance IDs, normalizes bounding boxes to [0, 1]
    page-space, and attaches a raster handle for downstream stages.
    """
    w = page.width_pt
    h = page.height_pt
    pn = page.page_number

    text_primitives = [_convert_text_block(block, pn, w, h) for block in page.text_blocks]
    image_primitives = [_convert_image(img, pn, w, h) for img in page.images]
    table_primitives = [_convert_table(tbl, pn, w, h) for tbl in page.tables]

    font_summary = _build_font_summary(page)

    raster_handle = PageRasterHandle(
        source_pdf_sha256=page.source_pdf_sha256,
        page_number=pn,
        width_pt=w,
        height_pt=h,
    )

    return PrimitivePageEvidence(
        page_number=pn,
        doc_id=page.doc_id,
        width_pt=w,
        height_pt=h,
        rotation=page.rotation,
        source_pdf_sha256=page.source_pdf_sha256,
        text_primitives=text_primitives,
        image_primitives=image_primitives,
        table_primitives=table_primitives,
        font_summary=font_summary,
        char_count=page.char_count,
        extraction_method="pymupdf",
        raster_handle=raster_handle,
    )


def _convert_text_block(
    block: TextBlock, page_number: int, width_pt: float, height_pt: float
) -> TextPrimitiveEvidence:
    """Convert a raw TextBlock to provenance-tagged evidence."""
    bbox_norm = normalize_bbox(block.bbox, width_pt, height_pt)

    # Derive dominant font from first span
    font_name = ""
    font_size = 0.0
    is_bold = False
    is_italic = False
    if block.lines and block.lines[0].spans:
        first_span = block.lines[0].spans[0]
        font_name = first_span.font.name
        font_size = first_span.font.size
        is_bold = first_span.font.is_bold
        is_italic = first_span.font.is_italic

    return TextPrimitiveEvidence(
        primitive_id=primitive_id("text", page_number, block.block_index),
        bbox_norm=bbox_norm,
        text=block.text,
        line_count=len(block.lines),
        font_name=font_name,
        font_size=font_size,
        is_bold=is_bold,
        is_italic=is_italic,
    )


def _convert_image(
    img: RawImageInfo, page_number: int, width_pt: float, height_pt: float
) -> ImagePrimitiveEvidence:
    """Convert a raw image to provenance-tagged evidence."""
    bbox_norm = normalize_bbox(img.bbox, width_pt, height_pt)

    return ImagePrimitiveEvidence(
        primitive_id=primitive_id("image", page_number, img.image_index),
        bbox_norm=bbox_norm,
        content_hash=img.content_hash,
        width_px=img.width,
        height_px=img.height,
        colorspace=img.colorspace,
    )


def _convert_table(
    tbl: RawTableInfo, page_number: int, width_pt: float, height_pt: float
) -> TablePrimitiveEvidence:
    """Convert a raw table to provenance-tagged evidence."""
    bbox_norm = normalize_bbox(tbl.bbox, width_pt, height_pt)

    return TablePrimitiveEvidence(
        primitive_id=primitive_id("table", page_number, tbl.table_index),
        bbox_norm=bbox_norm,
        rows=tbl.rows,
        cols=tbl.cols,
        cell_count=len(tbl.cells),
    )


def _build_font_summary(page: ExtractedPage) -> FontSummary:
    """Build aggregated font statistics from an extracted page."""
    font_counter: Counter[str] = Counter()
    size_counter: Counter[float] = Counter()

    for block in page.text_blocks:
        for line in block.lines:
            for span in line.spans:
                char_count = len(span.text)
                font_counter[span.font.name] += char_count
                size_counter[span.font.size] += char_count

    dominant_font = font_counter.most_common(1)[0][0] if font_counter else ""
    dominant_size = size_counter.most_common(1)[0][0] if size_counter else 0.0

    return FontSummary(
        dominant_font=dominant_font,
        dominant_size=dominant_size,
        unique_font_count=len(font_counter),
    )
