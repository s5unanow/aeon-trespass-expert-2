"""Shared primitive builders for Architecture 3 golden tests.

Provides helper functions for constructing synthetic PrimitivePageEvidence
fixtures without PDF or network access. Used by topology goldens,
evidence goldens, and any future test that needs controlled page layouts.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOC_ID = "topology-fixture"
PAGE_W = 612.0
PAGE_H = 792.0


# ---------------------------------------------------------------------------
# Primitive builders
# ---------------------------------------------------------------------------


def text(
    pid_idx: int, page: int, x0: float, y0: float, x1: float, y1: float, text_str: str
) -> TextPrimitiveEvidence:
    return TextPrimitiveEvidence(
        primitive_id=f"text:p{page:04d}:{pid_idx:03d}",
        bbox_norm=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text=text_str,
        line_count=1,
        font_name="Helvetica",
        font_size=10.0,
    )


def image(
    pid_idx: int,
    page: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    content_hash: str = "img_hash",
) -> ImagePrimitiveEvidence:
    return ImagePrimitiveEvidence(
        primitive_id=f"image:p{page:04d}:{pid_idx:03d}",
        bbox_norm=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        content_hash=content_hash,
        width_px=200,
        height_px=200,
    )


def table(  # noqa: PLR0913
    pid_idx: int,
    page: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    rows: int = 3,
    cols: int = 3,
    strategy: str = "lines_strict",
) -> TablePrimitiveEvidence:
    return TablePrimitiveEvidence(
        primitive_id=f"table:p{page:04d}:{pid_idx:03d}",
        bbox_norm=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        rows=rows,
        cols=cols,
        cell_count=rows * cols,
        extraction_strategy=strategy,
        area_fraction=round((x1 - x0) * (y1 - y0), 4),
    )


def drawing(
    pid_idx: int, page: int, x0: float, y0: float, x1: float, y1: float
) -> DrawingPrimitiveEvidence:
    return DrawingPrimitiveEvidence(
        primitive_id=f"drawing:p{page:04d}:{pid_idx:03d}",
        bbox_norm=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
        path_count=4,
        is_decorative=False,
    )


def page(
    page_number: int,
    *,
    doc_id: str = DOC_ID,
    text_prims: list[TextPrimitiveEvidence] | None = None,
    images: list[ImagePrimitiveEvidence] | None = None,
    tables: list[TablePrimitiveEvidence] | None = None,
    drawings: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id=doc_id,
        width_pt=PAGE_W,
        height_pt=PAGE_H,
        text_primitives=text_prims or [],
        image_primitives=images or [],
        table_primitives=tables or [],
        drawing_primitives=drawings or [],
    )


def empty_furniture(doc_id: str = DOC_ID) -> DocumentFurnitureProfile:
    return DocumentFurnitureProfile(doc_id=doc_id, total_pages_analyzed=1)
