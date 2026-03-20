"""Evidence-layer contracts for Architecture 3.

These models define the intermediate representations between raw extraction
(ExtractedPage) and semantic IR (PageRecord). They establish a provenance
chain:

    extraction -> primitive evidence -> canonical evidence -> resolved IR

Contract flow: Python (Pydantic) -> JSON Schema (internal pipeline only).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared geometry
# ---------------------------------------------------------------------------


class NormalizedBBox(BaseModel):
    """Bounding box in normalized page-space coordinates [0, 1].

    Origin is top-left: (0, 0) = top-left corner, (1, 1) = bottom-right.
    """

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Primitive evidence — immutable extraction record
# ---------------------------------------------------------------------------


class TextPrimitiveEvidence(BaseModel):
    """Provenance-tagged text primitive from extraction."""

    primitive_id: str
    bbox_norm: NormalizedBBox
    text: str
    line_count: int = 0
    font_name: str = ""
    font_size: float = 0.0
    is_bold: bool = False
    is_italic: bool = False


class ImagePrimitiveEvidence(BaseModel):
    """Provenance-tagged image primitive from extraction."""

    primitive_id: str
    bbox_norm: NormalizedBBox
    content_hash: str
    width_px: int = 0
    height_px: int = 0
    colorspace: str = ""


class TablePrimitiveEvidence(BaseModel):
    """Provenance-tagged table primitive from extraction."""

    primitive_id: str
    bbox_norm: NormalizedBBox
    rows: int = 0
    cols: int = 0
    cell_count: int = 0


class DrawingPrimitiveEvidence(BaseModel):
    """Provenance-tagged vector drawing primitive from extraction."""

    primitive_id: str
    bbox_norm: NormalizedBBox
    path_count: int = 0
    is_decorative: bool = False


class FontSummary(BaseModel):
    """Aggregated font statistics for a page."""

    dominant_font: str = ""
    dominant_size: float = 0.0
    unique_font_count: int = 0


class PrimitivePageEvidence(BaseModel):
    """Immutable extraction evidence for a single page.

    Produced after extract_primitives. Contains provenance-tagged
    primitives with normalized coordinates. This is the stable evidence
    layer that downstream stages (region segmentation, reading order,
    asset resolution) consume -- never mutated after creation.

    Artifact path: ``{run}/evidence/p{page_number:04d}_primitive.json``
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float
    rotation: int = 0
    source_pdf_sha256: str = ""

    text_primitives: list[TextPrimitiveEvidence] = Field(default_factory=list)
    image_primitives: list[ImagePrimitiveEvidence] = Field(default_factory=list)
    table_primitives: list[TablePrimitiveEvidence] = Field(default_factory=list)
    drawing_primitives: list[DrawingPrimitiveEvidence] = Field(default_factory=list)

    font_summary: FontSummary = Field(default_factory=FontSummary)
    char_count: int = 0
    extraction_method: str = "pdfplumber"


# ---------------------------------------------------------------------------
# Canonical evidence — topology and entity analysis results
# ---------------------------------------------------------------------------


class CanonicalPageEvidence(BaseModel):
    """Canonical page evidence after topology and entity analysis.

    Produced after region segmentation, reading-order reconstruction,
    and asset/entity resolution. Contains page-level graph outputs
    that semantic block building consumes.

    Fields for region graphs, reading order, asset occurrences, and
    symbol candidates will be added by Phase 2 and Phase 3 issues
    (S5U-254 through S5U-262).

    Artifact path: ``{run}/evidence/p{page_number:04d}_canonical.json``
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float

    primitive_evidence_hash: str = ""

    estimated_column_count: int = 1
    has_tables: bool = False
    has_figures: bool = False
    has_callouts: bool = False
    furniture_fraction: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Resolved page IR — ready for semantic block building
# ---------------------------------------------------------------------------


class ResolvedPageIR(BaseModel):
    """Fully resolved page IR ready for semantic block building.

    Bridges evidence analysis and PageRecord construction. Contains
    the resolved render mode, confidence signals, and provenance
    references that determine how semantic blocks are built.

    Confidence scoring details will be added by S5U-263.

    Artifact path: ``{run}/resolved/p{page_number:04d}.json``
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float

    canonical_evidence_hash: str = ""

    render_mode: Literal["semantic", "hybrid", "facsimile"] = "semantic"
    fallback_image_ref: str | None = None

    page_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_reasons: list[str] = Field(default_factory=list)

    source_pdf_sha256: str = ""
