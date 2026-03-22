"""Evidence-layer contracts.

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
    extraction_strategy: str = "default"
    area_fraction: float = 0.0


class DrawingPrimitiveEvidence(BaseModel):
    """Provenance-tagged vector drawing primitive from extraction."""

    primitive_id: str
    bbox_norm: NormalizedBBox
    path_count: int = 0
    is_decorative: bool = False


class PageRasterHandle(BaseModel):
    """Reference for obtaining a page raster image.

    Provides downstream stages with an explicit handle to request page
    rasters instead of assuming they can re-open the PDF ad hoc.
    If ``raster_path`` is set, a pre-rendered raster is available on disk.
    """

    source_pdf_sha256: str
    page_number: int
    width_pt: float
    height_pt: float
    raster_path: str | None = None
    default_dpi: int = 150


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
    raster_handle: PageRasterHandle | None = None


# ---------------------------------------------------------------------------
# Furniture and template detection (S5U-254)
# ---------------------------------------------------------------------------

FurnitureType = Literal[
    "header",
    "footer",
    "page_number",
    "border",
    "background_panel",
    "divider",
    "ornament",
]


class FurnitureCandidate(BaseModel):
    """A primitive identified as document-level furniture (repeated across pages)."""

    candidate_id: str
    furniture_type: FurnitureType
    bbox_norm: NormalizedBBox
    source_primitive_kind: Literal["text", "image", "drawing"]
    page_numbers: list[int] = Field(default_factory=list)
    repetition_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    text_sample: str = ""
    content_hash: str = ""
    path_count: int = 0


class TemplateAssignment(BaseModel):
    """Assignment of pages to a detected page template/archetype."""

    template_id: str
    page_numbers: list[int] = Field(default_factory=list)
    furniture_ids: list[str] = Field(default_factory=list)
    description: str = ""


class DocumentFurnitureProfile(BaseModel):
    """Document-level furniture detection results.

    Produced by collect_evidence once per document (not per page).
    Consumed by downstream stages to subtract furniture from content regions.

    Artifact path: ``{run}/evidence/furniture_profile.json``
    """

    doc_id: str
    total_pages_analyzed: int
    furniture_candidates: list[FurnitureCandidate] = Field(default_factory=list)
    templates: list[TemplateAssignment] = Field(default_factory=list)
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Region segmentation (S5U-255)
# ---------------------------------------------------------------------------

RegionKind = Literal[
    "main_flow",
    "column",
    "band",
    "sidebar",
    "callout",
    "figure",
    "table",
    "caption",
    "decoration",
    "furniture",
    "unknown",
]


class RegionConfidence(BaseModel):
    """Confidence score with supporting reasons."""

    value: float = Field(default=1.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class RegionCandidate(BaseModel):
    """A spatial partition of a page with a semantic kind hint.

    Regions are geometric hypotheses — ``kind_hint`` may be refined
    by later entity resolution stages.
    """

    region_id: str
    kind_hint: RegionKind
    bbox: NormalizedBBox
    parent_region_id: str | None = None
    band_index: int | None = None
    column_index: int | None = None
    source_evidence_ids: list[str] = Field(default_factory=list)
    features: dict[str, float | int | str | bool] = Field(default_factory=dict)
    confidence: RegionConfidence = Field(default_factory=RegionConfidence)


class RegionEdge(BaseModel):
    """A typed relationship between two regions in a page region graph."""

    edge_type: Literal["contains", "overlaps", "adjacent_to", "interrupts"]
    src_region_id: str
    dst_region_id: str


class PageRegionGraph(BaseModel):
    """Region segmentation graph for a single page.

    Produced by collect_evidence after furniture subtraction. Contains
    spatial partitions with containment/adjacency relationships that
    downstream stages (reading order, entity resolution) consume.

    Artifact path: ``{run}/evidence/p{page_number:04d}_regions.json``
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float
    regions: list[RegionCandidate] = Field(default_factory=list)
    edges: list[RegionEdge] = Field(default_factory=list)
    furniture_ids_excluded: list[str] = Field(default_factory=list)
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Reading order (S5U-256)
# ---------------------------------------------------------------------------

FlowRole = Literal[
    "main",
    "aside",
    "interruption",
]


class ReadingOrderEntry(BaseModel):
    """A single step in the linearised reading order.

    Each entry references a region from the PageRegionGraph and carries
    flow metadata so downstream stages know how to integrate the content.
    """

    sequence_index: int = Field(ge=0)
    region_id: str
    kind_hint: RegionKind
    flow_role: FlowRole = "main"
    band_index: int | None = None
    column_index: int | None = None
    confidence: RegionConfidence = Field(default_factory=RegionConfidence)


class PageReadingOrder(BaseModel):
    """Linearised reading order for a single page.

    Produced from the PageRegionGraph by traversing bands top-to-bottom,
    columns left-to-right within each band, and emitting figures, tables,
    and callouts at their band position. Sidebars and callouts are tagged
    with ``flow_role="aside"``; full-width elements that interrupt a
    multi-column flow are tagged ``flow_role="interruption"``.

    Artifact path: ``{run}/evidence/p{page_number:04d}_reading_order.json``
    """

    page_number: int
    doc_id: str
    entries: list[ReadingOrderEntry] = Field(default_factory=list)
    total_regions: int = 0
    unassigned_region_ids: list[str] = Field(default_factory=list)
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Asset registry (S5U-257)
# ---------------------------------------------------------------------------

AssetKind = Literal["raster", "vector_cluster", "unresolved_visual"]

OccurrenceContext = Literal[
    "inline",
    "figure",
    "decoration",
    "list_marker",
    "legend",
    "unknown",
]


class AssetOccurrence(BaseModel):
    """A single occurrence of an asset on a specific page."""

    occurrence_id: str
    page_number: int
    bbox_norm: NormalizedBBox
    source_primitive_id: str
    context_hint: OccurrenceContext = "unknown"


class AssetClass(BaseModel):
    """A deduplicated asset identity across the document.

    Rasters use ``content_hash`` for exact identity. Vector clusters
    use ``path_count`` and position fingerprints for fuzzy identity.
    """

    asset_class_id: str
    kind: AssetKind
    content_hash: str = ""
    width_px: int = 0
    height_px: int = 0
    colorspace: str = ""
    path_count: int = 0
    occurrence_count: int = 0
    page_numbers: list[int] = Field(default_factory=list)
    occurrences: list[AssetOccurrence] = Field(default_factory=list)
    is_furniture: bool = False


class DocumentAssetRegistry(BaseModel):
    """Document-level asset registry.

    Produced by collect_evidence once per document. Tracks every
    visual asset class and its occurrences across pages, enabling
    cross-page deduplication, symbol detection, and figure grouping.

    Artifact path: ``{run}/evidence/asset_registry.json``
    """

    doc_id: str
    total_pages_analyzed: int
    asset_classes: list[AssetClass] = Field(default_factory=list)
    total_occurrences: int = 0
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Symbol candidates (S5U-258)
# ---------------------------------------------------------------------------

SymbolEvidenceSource = Literal[
    "text_token",
    "raster_hash",
    "vector_signature",
    "text_dingbat",
]

SymbolAnchorType = Literal[
    "inline",
    "line_prefix",
    "cell_local",
    "block_attached",
    "region_decoration",
]


class SymbolCandidate(BaseModel):
    """A single symbol candidate detected from evidence.

    Classified candidates have a non-empty ``symbol_id``. Unclassified
    candidates (e.g. dingbats not in the symbol pack) are preserved for
    review by downstream QA rules.

    Each candidate records its evidence source and the metadata required
    to trace the detection back to a specific primitive or asset class.
    """

    candidate_id: str
    page_number: int
    evidence_source: SymbolEvidenceSource
    bbox_norm: NormalizedBBox
    source_primitive_id: str = ""
    source_asset_class_id: str = ""

    # Classification result
    symbol_id: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_classified: bool = False

    # Evidence metadata (populated per source type)
    matched_token: str = ""
    matched_hash: str = ""
    matched_signature: str = ""
    codepoint: str = ""
    codepoint_name: str = ""

    is_decorative: bool = False

    anchor_type: SymbolAnchorType = "inline"


class PageSymbolCandidates(BaseModel):
    """Symbol candidates for a single page.

    Artifact path: ``{run}/evidence/p{page_number:04d}_symbol_candidates.json``
    """

    page_number: int
    doc_id: str
    candidates: list[SymbolCandidate] = Field(default_factory=list)
    classified_count: int = 0
    unclassified_count: int = 0
    detection_version: str = "0.1.0"


class DocumentSymbolSummary(BaseModel):
    """Document-level symbol detection summary.

    Artifact path: ``{run}/evidence/symbol_summary.json``
    """

    doc_id: str
    total_pages_analyzed: int
    total_candidates: int = 0
    classified_count: int = 0
    unclassified_count: int = 0
    symbols_found: list[str] = Field(default_factory=list)
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Figure-caption linking (S5U-260)
# ---------------------------------------------------------------------------


class FigureCaptionLink(BaseModel):
    """A scored link between a figure region and its caption.

    Produced by spatial scoring (v3) or sequential block-order matching (v2).
    Persisted as part of ``PageFigureCaptionLinks`` for review/debugging.
    """

    figure_id: str
    caption_id: str
    figure_block_id: str = ""
    caption_block_id: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    x_overlap_ratio: float = 0.0
    y_distance_norm: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class PageFigureCaptionLinks(BaseModel):
    """Figure-caption linkage artifact for a single page.

    Artifact path: ``{run}/resolve_assets_symbols/p{page_number:04d}_figure_caption_links.json``
    """

    page_number: int
    doc_id: str
    links: list[FigureCaptionLink] = Field(default_factory=list)
    method: Literal["spatial", "sequential"] = "sequential"
    detection_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# Canonical evidence — topology and entity analysis results
# ---------------------------------------------------------------------------


class CanonicalPageEvidence(BaseModel):
    """Canonical page evidence after topology and entity analysis.

    Produced after region segmentation, reading-order reconstruction,
    and asset/entity resolution. Contains page-level graph outputs
    that semantic block building consumes.

    Region graph added by S5U-255 (Phase 2). Reading order added by
    S5U-256 (Phase 2). Asset registry added by S5U-257 (Phase 3).
    Symbol candidates will be added by S5U-258 through S5U-262.

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
    furniture_ids: list[str] = Field(default_factory=list)
    template_id: str = ""

    region_graph: PageRegionGraph | None = None
    reading_order: PageReadingOrder | None = None
    asset_occurrence_ids: list[str] = Field(default_factory=list)
    symbol_candidate_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolved page IR — ready for semantic block building
# ---------------------------------------------------------------------------


class ResolvedPageIR(BaseModel):
    """Fully resolved page IR ready for semantic block building.

    Bridges evidence analysis and PageRecord construction. Contains
    the resolved render mode, confidence signals, and provenance
    references that determine how semantic blocks are built.

    Confidence is scored from canonical evidence signals (region quality,
    reading-order quality, layout complexity, entity density) and mapped
    to a render mode via deterministic thresholds (S5U-263).

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
