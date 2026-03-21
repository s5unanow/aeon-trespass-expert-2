"""Page region segmentation from primitive evidence and furniture profile.

Builds a PageRegionGraph by:
  1. Masking furniture primitives
  2. Detecting horizontal bands (full-width gaps/elements)
  3. Detecting columns within each band (vertical gutters)
  4. Identifying figure, table, and container candidate regions
  5. Emitting containment and adjacency edges

Pure functions — no IO or stage dependencies.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    NormalizedBBox,
    PageRegionGraph,
    PrimitivePageEvidence,
    RegionCandidate,
    RegionConfidence,
    RegionEdge,
)

# Columns narrower than this fraction of band width are classified as sidebars
_SIDEBAR_WIDTH_RATIO = 0.35

# Minimum area (normalized page fraction) for a drawing to be a callout
_CALLOUT_MIN_AREA = 0.005


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def segment_page_regions(
    primitive: PrimitivePageEvidence,
    furniture_profile: DocumentFurnitureProfile,
    furniture_ids_for_page: list[str],
    *,
    min_gap_fraction: float = 0.03,
    min_gutter_fraction: float = 0.02,
) -> PageRegionGraph:
    """Build a PageRegionGraph for a single page.

    Args:
        primitive: The page's primitive evidence.
        furniture_profile: Document-level furniture profile.
        furniture_ids_for_page: Furniture candidate IDs active on this page.
        min_gap_fraction: Minimum vertical gap (as fraction of page height)
            to split bands.
        min_gutter_fraction: Minimum horizontal gap (as fraction of page width)
            to split columns.

    Returns:
        A PageRegionGraph with regions, edges, and furniture exclusion info.
    """
    furniture_bboxes = _collect_furniture_bboxes(furniture_profile, furniture_ids_for_page)
    content_prims = _filter_non_furniture_primitives(primitive, furniture_bboxes)

    regions: list[RegionCandidate] = []
    edges: list[RegionEdge] = []
    region_counter = 0

    # Detect bands (horizontal partitioning)
    bands = _detect_bands(content_prims, min_gap_fraction)

    for band_idx, band in enumerate(bands):
        band_id = f"reg:{primitive.page_number}:{region_counter}"
        region_counter += 1

        band_region = RegionCandidate(
            region_id=band_id,
            kind_hint="band",
            bbox=band.bbox,
            band_index=band_idx,
            source_evidence_ids=band.primitive_ids,
            features={"primitive_count": len(band.primitive_ids)},
            confidence=RegionConfidence(value=0.9, reasons=["horizontal_partition"]),
        )
        regions.append(band_region)

        # Detect columns within band
        columns = _detect_columns(band, min_gutter_fraction)

        if len(columns) > 1:
            band_region.features["column_count"] = len(columns)
            band_width = band.bbox.x1 - band.bbox.x0
            for col_idx, col in enumerate(columns):
                col_id = f"reg:{primitive.page_number}:{region_counter}"
                region_counter += 1
                col_width = col.bbox.x1 - col.bbox.x0
                is_sidebar = band_width > 0 and col_width / band_width < _SIDEBAR_WIDTH_RATIO
                col_region = RegionCandidate(
                    region_id=col_id,
                    kind_hint="sidebar" if is_sidebar else "column",
                    bbox=col.bbox,
                    parent_region_id=band_id,
                    band_index=band_idx,
                    column_index=col_idx,
                    source_evidence_ids=col.primitive_ids,
                    features={"text_count": len(col.primitive_ids)},
                    confidence=RegionConfidence(
                        value=0.7 if is_sidebar else 0.85,
                        reasons=["narrow_column_sidebar"] if is_sidebar else ["gutter_detected"],
                    ),
                )
                regions.append(col_region)
                edges.append(
                    RegionEdge(
                        edge_type="contains",
                        src_region_id=band_id,
                        dst_region_id=col_id,
                    )
                )
        else:
            band_region.features["column_count"] = 1

        # Detect figure regions inside band
        figure_regions, fig_counter = _detect_figure_regions(
            band, primitive.page_number, region_counter, band_id, band_idx
        )
        region_counter = fig_counter
        for fig_region in figure_regions:
            regions.append(fig_region)
            edges.append(
                RegionEdge(
                    edge_type="contains",
                    src_region_id=band_id,
                    dst_region_id=fig_region.region_id,
                )
            )

        # Detect table regions inside band
        table_regions, tbl_counter = _detect_table_regions(
            band, primitive.page_number, region_counter, band_id, band_idx
        )
        region_counter = tbl_counter
        for tbl_region in table_regions:
            regions.append(tbl_region)
            edges.append(
                RegionEdge(
                    edge_type="contains",
                    src_region_id=band_id,
                    dst_region_id=tbl_region.region_id,
                )
            )

        # Detect callout regions (drawing-enclosed text)
        callout_regions, callout_counter = _detect_callout_regions(
            band, primitive.page_number, region_counter, band_id, band_idx
        )
        region_counter = callout_counter
        for callout_region in callout_regions:
            regions.append(callout_region)
            edges.append(
                RegionEdge(
                    edge_type="contains",
                    src_region_id=band_id,
                    dst_region_id=callout_region.region_id,
                )
            )

    # Add adjacency edges between consecutive bands
    band_regions = [r for r in regions if r.kind_hint == "band"]
    for i in range(len(band_regions) - 1):
        edges.append(
            RegionEdge(
                edge_type="adjacent_to",
                src_region_id=band_regions[i].region_id,
                dst_region_id=band_regions[i + 1].region_id,
            )
        )

    return PageRegionGraph(
        page_number=primitive.page_number,
        doc_id=primitive.doc_id,
        width_pt=primitive.width_pt,
        height_pt=primitive.height_pt,
        regions=regions,
        edges=edges,
        furniture_ids_excluded=furniture_ids_for_page,
    )


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class _PrimRef:
    """Lightweight reference to a primitive's ID, kind, and bbox."""

    __slots__ = ("bbox", "features", "kind", "primitive_id")

    def __init__(
        self,
        primitive_id: str,
        bbox: NormalizedBBox,
        kind: str,
        features: dict[str, float | int | str] | None = None,
    ) -> None:
        self.primitive_id = primitive_id
        self.bbox = bbox
        self.kind = kind
        self.features: dict[str, float | int | str] = features or {}


class _Band:
    """A horizontal slice of the page containing primitives."""

    __slots__ = ("bbox", "primitive_ids", "prims")

    def __init__(
        self,
        bbox: NormalizedBBox,
        prims: list[_PrimRef],
    ) -> None:
        self.bbox = bbox
        self.primitive_ids = [p.primitive_id for p in prims]
        self.prims = prims


class _Column:
    """A vertical column within a band."""

    __slots__ = ("bbox", "primitive_ids")

    def __init__(self, bbox: NormalizedBBox, primitive_ids: list[str]) -> None:
        self.bbox = bbox
        self.primitive_ids = primitive_ids


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bbox_overlaps(a: NormalizedBBox, b: NormalizedBBox) -> bool:
    """Check if two bboxes overlap."""
    return a.x0 < b.x1 and a.x1 > b.x0 and a.y0 < b.y1 and a.y1 > b.y0


def _collect_furniture_bboxes(
    profile: DocumentFurnitureProfile,
    furniture_ids: list[str],
) -> list[NormalizedBBox]:
    """Get bboxes for the given furniture candidate IDs."""
    id_set = set(furniture_ids)
    return [c.bbox_norm for c in profile.furniture_candidates if c.candidate_id in id_set]


def _filter_non_furniture_primitives(
    primitive: PrimitivePageEvidence,
    furniture_bboxes: list[NormalizedBBox],
) -> list[_PrimRef]:
    """Return all primitives that don't substantially overlap with furniture."""
    refs: list[_PrimRef] = []

    for tp in primitive.text_primitives:
        if not _overlaps_any_furniture(tp.bbox_norm, furniture_bboxes):
            refs.append(_PrimRef(tp.primitive_id, tp.bbox_norm, "text"))

    for ip in primitive.image_primitives:
        if not _overlaps_any_furniture(ip.bbox_norm, furniture_bboxes):
            refs.append(_PrimRef(ip.primitive_id, ip.bbox_norm, "image"))

    for tbp in primitive.table_primitives:
        if not _overlaps_any_furniture(tbp.bbox_norm, furniture_bboxes):
            refs.append(
                _PrimRef(
                    tbp.primitive_id,
                    tbp.bbox_norm,
                    "table",
                    features={
                        "rows": tbp.rows,
                        "cols": tbp.cols,
                        "cell_count": tbp.cell_count,
                        "extraction_strategy": tbp.extraction_strategy,
                        "area_fraction": tbp.area_fraction,
                    },
                )
            )

    for dp in primitive.drawing_primitives:
        if not dp.is_decorative and not _overlaps_any_furniture(dp.bbox_norm, furniture_bboxes):
            refs.append(_PrimRef(dp.primitive_id, dp.bbox_norm, "drawing"))

    return refs


def _overlaps_any_furniture(
    bbox: NormalizedBBox,
    furniture_bboxes: list[NormalizedBBox],
) -> bool:
    """Check if a primitive bbox substantially overlaps any furniture bbox."""
    for fb in furniture_bboxes:
        if _bbox_overlaps(bbox, fb):
            # Check if the overlap is substantial (>50% of primitive area)
            prim_area = _bbox_area(bbox)
            if prim_area <= 0:
                return True
            overlap = _overlap_area(bbox, fb)
            if overlap / prim_area > 0.5:
                return True
    return False


def _bbox_area(bbox: NormalizedBBox) -> float:
    w = max(0.0, bbox.x1 - bbox.x0)
    h = max(0.0, bbox.y1 - bbox.y0)
    return w * h


def _overlap_area(a: NormalizedBBox, b: NormalizedBBox) -> float:
    x0 = max(a.x0, b.x0)
    y0 = max(a.y0, b.y0)
    x1 = min(a.x1, b.x1)
    y1 = min(a.y1, b.y1)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _detect_bands(
    prims: list[_PrimRef],
    min_gap_fraction: float,
) -> list[_Band]:
    """Partition primitives into horizontal bands separated by vertical gaps.

    Primitives are sorted by y0, then consecutive primitives with a vertical
    gap exceeding ``min_gap_fraction`` are split into separate bands.
    """
    if not prims:
        return []

    sorted_prims = sorted(prims, key=lambda p: p.bbox.y0)

    bands: list[_Band] = []
    current_prims: list[_PrimRef] = [sorted_prims[0]]
    current_y1 = sorted_prims[0].bbox.y1

    for prim in sorted_prims[1:]:
        gap = prim.bbox.y0 - current_y1
        if gap >= min_gap_fraction:
            # Start a new band
            bands.append(_make_band(current_prims))
            current_prims = [prim]
            current_y1 = prim.bbox.y1
        else:
            current_prims.append(prim)
            current_y1 = max(current_y1, prim.bbox.y1)

    if current_prims:
        bands.append(_make_band(current_prims))

    return bands


def _make_band(prims: list[_PrimRef]) -> _Band:
    """Create a _Band from a list of primitives."""
    x0 = min(p.bbox.x0 for p in prims)
    y0 = min(p.bbox.y0 for p in prims)
    x1 = max(p.bbox.x1 for p in prims)
    y1 = max(p.bbox.y1 for p in prims)
    bbox = NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)
    return _Band(bbox, prims)


def _detect_columns(
    band: _Band,
    min_gutter_fraction: float,
) -> list[_Column]:
    """Detect columns within a band by finding persistent vertical gutters.

    Returns a list of columns. If no gutter is found, returns a single
    column spanning the full band.
    """
    if len(band.prims) < 2:
        return [
            _Column(
                bbox=band.bbox,
                primitive_ids=band.primitive_ids,
            )
        ]

    # Sort primitives by x-center for gutter analysis
    sorted_prims = sorted(band.prims, key=lambda p: (p.bbox.x0 + p.bbox.x1) / 2)

    # Find the largest horizontal gap between consecutive primitive extents
    # Build intervals of occupied x-ranges
    intervals = [(p.bbox.x0, p.bbox.x1) for p in sorted_prims]
    merged = _merge_intervals(intervals)

    if len(merged) < 2:
        return [_Column(bbox=band.bbox, primitive_ids=band.primitive_ids)]

    # Find gaps between merged intervals
    best_gap = 0.0
    best_gap_x = 0.0
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        gap = gap_end - gap_start
        if gap > best_gap:
            best_gap = gap
            best_gap_x = (gap_start + gap_end) / 2

    if best_gap < min_gutter_fraction:
        return [_Column(bbox=band.bbox, primitive_ids=band.primitive_ids)]

    # Split primitives at the gutter
    left_prims: list[str] = []
    right_prims: list[str] = []
    left_x0, left_x1 = band.bbox.x1, band.bbox.x0
    right_x0, right_x1 = band.bbox.x1, band.bbox.x0
    left_y0, left_y1 = band.bbox.y1, band.bbox.y0
    right_y0, right_y1 = band.bbox.y1, band.bbox.y0

    for prim in band.prims:
        center_x = (prim.bbox.x0 + prim.bbox.x1) / 2
        if center_x < best_gap_x:
            left_prims.append(prim.primitive_id)
            left_x0 = min(left_x0, prim.bbox.x0)
            left_x1 = max(left_x1, prim.bbox.x1)
            left_y0 = min(left_y0, prim.bbox.y0)
            left_y1 = max(left_y1, prim.bbox.y1)
        else:
            right_prims.append(prim.primitive_id)
            right_x0 = min(right_x0, prim.bbox.x0)
            right_x1 = max(right_x1, prim.bbox.x1)
            right_y0 = min(right_y0, prim.bbox.y0)
            right_y1 = max(right_y1, prim.bbox.y1)

    columns: list[_Column] = []
    if left_prims:
        columns.append(
            _Column(
                bbox=NormalizedBBox(x0=left_x0, y0=left_y0, x1=left_x1, y1=left_y1),
                primitive_ids=left_prims,
            )
        )
    if right_prims:
        columns.append(
            _Column(
                bbox=NormalizedBBox(x0=right_x0, y0=right_y0, x1=right_x1, y1=right_y1),
                primitive_ids=right_prims,
            )
        )

    return columns if columns else [_Column(bbox=band.bbox, primitive_ids=band.primitive_ids)]


def _merge_intervals(
    intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Merge overlapping intervals."""
    if not intervals:
        return []
    sorted_ivs = sorted(intervals)
    merged: list[tuple[float, float]] = [sorted_ivs[0]]
    for start, end in sorted_ivs[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _detect_figure_regions(
    band: _Band,
    page_number: int,
    counter: int,
    parent_id: str,
    band_idx: int,
) -> tuple[list[RegionCandidate], int]:
    """Detect figure candidate regions from image primitives in the band."""
    regions: list[RegionCandidate] = []
    for prim in band.prims:
        if prim.kind == "image":
            region_id = f"reg:{page_number}:{counter}"
            counter += 1
            regions.append(
                RegionCandidate(
                    region_id=region_id,
                    kind_hint="figure",
                    bbox=prim.bbox,
                    parent_region_id=parent_id,
                    band_index=band_idx,
                    source_evidence_ids=[prim.primitive_id],
                    confidence=RegionConfidence(value=0.8, reasons=["image_primitive"]),
                )
            )
    return regions, counter


def _score_table_confidence(
    prim: _PrimRef,
    band: _Band,
) -> RegionConfidence:
    """Compute region confidence for a table primitive using provenance metadata.

    Factors:
    - Extraction strategy: ``lines_strict`` tables are high confidence.
    - Structure: single-cell tables are likely decorative boxes.
    - Text overlap: a table bbox that contains many text primitives may be a
      decorative border rather than a real data table.
    """
    reasons: list[str] = ["table_primitive"]
    strategy = str(prim.features.get("extraction_strategy", "default"))
    rows = int(prim.features.get("rows", 0))
    cols = int(prim.features.get("cols", 0))
    cell_count = int(prim.features.get("cell_count", 0))

    # Base confidence from extraction strategy
    if strategy == "lines_strict":
        score = 0.9
        reasons.append("strategy:lines_strict")
    elif strategy == "lines":
        score = 0.8
        reasons.append("strategy:lines")
    else:
        score = 0.7
        reasons.append(f"strategy:{strategy}")

    # Penalise degenerate tables (likely decorative boxes)
    if rows <= 1 and cols <= 1:
        score -= 0.25
        reasons.append("degenerate_1x1")
    elif cell_count <= 2:
        score -= 0.15
        reasons.append("very_few_cells")

    # Boost well-structured tables
    if rows >= 2 and cols >= 2 and cell_count >= 4:
        score += 0.05
        reasons.append("multi_row_col")

    # Check text-overlap: if more than half the band's text prims fall inside
    # the table bbox, the "table" is probably a decorative border/box.
    text_prims_in_band = [p for p in band.prims if p.kind == "text"]
    if text_prims_in_band:
        inside = sum(1 for tp in text_prims_in_band if _bbox_contains(prim.bbox, tp.bbox))
        overlap_ratio = inside / len(text_prims_in_band)
        if overlap_ratio > 0.5:
            score -= 0.2
            reasons.append("high_text_overlap")

    return RegionConfidence(value=max(0.0, min(1.0, round(score, 2))), reasons=reasons)


def _detect_table_regions(
    band: _Band,
    page_number: int,
    counter: int,
    parent_id: str,
    band_idx: int,
) -> tuple[list[RegionCandidate], int]:
    """Detect table candidate regions from table primitives in the band.

    Uses extraction strategy, structural metadata, and region context
    to assign confidence.  Degenerate tables (1x1 from decorative boxes)
    receive low confidence so downstream stages can filter them.
    """
    regions: list[RegionCandidate] = []
    for prim in band.prims:
        if prim.kind == "table":
            confidence = _score_table_confidence(prim, band)
            region_id = f"reg:{page_number}:{counter}"
            counter += 1
            regions.append(
                RegionCandidate(
                    region_id=region_id,
                    kind_hint="table",
                    bbox=prim.bbox,
                    parent_region_id=parent_id,
                    band_index=band_idx,
                    source_evidence_ids=[prim.primitive_id],
                    confidence=confidence,
                    features={
                        "rows": int(prim.features.get("rows", 0)),
                        "cols": int(prim.features.get("cols", 0)),
                        "extraction_strategy": str(
                            prim.features.get("extraction_strategy", "default")
                        ),
                    },
                )
            )
    return regions, counter


def _bbox_contains(outer: NormalizedBBox, inner: NormalizedBBox) -> bool:
    """Check if outer bbox fully contains inner bbox."""
    return (
        outer.x0 <= inner.x0
        and outer.y0 <= inner.y0
        and outer.x1 >= inner.x1
        and outer.y1 >= inner.y1
    )


def _detect_callout_regions(
    band: _Band,
    page_number: int,
    counter: int,
    parent_id: str,
    band_idx: int,
) -> tuple[list[RegionCandidate], int]:
    """Detect callout candidates from drawing primitives that enclose text.

    A callout is a non-decorative drawing with sufficient area that fully
    contains at least one text primitive — indicating a bordered text box.
    """
    drawing_prims = [p for p in band.prims if p.kind == "drawing"]
    text_prims = [p for p in band.prims if p.kind == "text"]

    if not drawing_prims or not text_prims:
        return [], counter

    regions: list[RegionCandidate] = []
    for drw in drawing_prims:
        if _bbox_area(drw.bbox) < _CALLOUT_MIN_AREA:
            continue
        enclosed = [t for t in text_prims if _bbox_contains(drw.bbox, t.bbox)]
        if not enclosed:
            continue
        region_id = f"reg:{page_number}:{counter}"
        counter += 1
        regions.append(
            RegionCandidate(
                region_id=region_id,
                kind_hint="callout",
                bbox=drw.bbox,
                parent_region_id=parent_id,
                band_index=band_idx,
                source_evidence_ids=[drw.primitive_id] + [t.primitive_id for t in enclosed],
                confidence=RegionConfidence(value=0.6, reasons=["drawing_encloses_text"]),
            )
        )
    return regions, counter
