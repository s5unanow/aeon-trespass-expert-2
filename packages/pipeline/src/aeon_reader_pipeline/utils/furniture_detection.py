"""Cross-page furniture detection and page-template classification.

Detects repeated visual/text elements (headers, footers, page numbers, borders)
across pages and assigns pages to template groups based on shared furniture.

Pure functions — no IO or stage dependencies.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from typing import Literal

from aeon_reader_pipeline.config.hashing import hash_string
from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    FurnitureCandidate,
    FurnitureType,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
    TemplateAssignment,
    TextPrimitiveEvidence,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:\d{1,4}|[ivxlcdm]{1,8}|[IVXLCDM]{1,8})\s*$",
)


def detect_furniture(
    primitives: list[PrimitivePageEvidence],
    *,
    min_repetition_rate: float = 0.5,
    edge_margin: float = 0.08,
    position_tolerance: float = 0.02,
) -> DocumentFurnitureProfile:
    """Detect document-level furniture from cross-page primitive evidence.

    Args:
        primitives: All pages' primitive evidence (must share a doc_id).
        min_repetition_rate: Minimum fraction of pages an element must appear
            on to be considered furniture (0.0-1.0).
        edge_margin: Fraction of page considered "edge zone" for classification.
        position_tolerance: Bbox rounding tolerance for position clustering.

    Returns:
        A DocumentFurnitureProfile with detected candidates and templates.
    """
    if len(primitives) < 2:
        doc_id = primitives[0].doc_id if primitives else ""
        return DocumentFurnitureProfile(
            doc_id=doc_id,
            total_pages_analyzed=len(primitives),
        )

    doc_id = primitives[0].doc_id
    total_pages = len(primitives)

    # Step 1+2: Build clusters from fingerprinted primitives
    clusters = _build_clusters(primitives, position_tolerance)

    # Build drawing path_count lookup for vector furniture cross-referencing
    drawing_path_counts: dict[str, int] = {}
    for page in primitives:
        for drw in page.drawing_primitives:
            drawing_path_counts[drw.primitive_id] = drw.path_count

    # Step 3: Filter by repetition rate and classify
    candidates: list[FurnitureCandidate] = []
    candidate_idx = 0

    for cluster in clusters.values():
        page_count = len({occ.page_number for occ in cluster})
        rate = page_count / total_pages
        if rate < min_repetition_rate:
            continue

        representative = cluster[0]
        median_bbox = _median_bbox(cluster)

        if not _passes_furniture_gates(representative, median_bbox, edge_margin):
            continue

        ftype = _classify_furniture_type(representative, median_bbox, edge_margin)
        pages = sorted({occ.page_number for occ in cluster})

        candidates.append(
            FurnitureCandidate(
                candidate_id=f"furn:{ftype}:{candidate_idx:03d}",
                furniture_type=ftype,
                bbox_norm=median_bbox,
                source_primitive_kind=representative.kind,
                page_numbers=pages,
                repetition_rate=rate,
                confidence=min(1.0, rate / min_repetition_rate),
                text_sample=representative.text_sample,
                content_hash=representative.content_hash,
                path_count=drawing_path_counts.get(representative.primitive_id, 0),
            )
        )
        candidate_idx += 1

    # Step 4: Assign templates
    templates = _assign_templates(candidates)

    return DocumentFurnitureProfile(
        doc_id=doc_id,
        total_pages_analyzed=total_pages,
        furniture_candidates=candidates,
        templates=templates,
    )


def compute_page_furniture(
    profile: DocumentFurnitureProfile,
) -> tuple[dict[int, list[str]], dict[int, str], dict[int, float]]:
    """Derive per-page furniture lookups from a DocumentFurnitureProfile.

    Returns:
        (page_furniture_ids, page_template_id, page_furniture_fraction)
        Each is a dict keyed by page_number.
    """
    page_furniture_ids: dict[int, list[str]] = defaultdict(list)
    page_template_id: dict[int, str] = {}
    page_furniture_fraction: dict[int, float] = defaultdict(float)

    for cand in profile.furniture_candidates:
        area = _bbox_area(cand.bbox_norm)
        for pn in cand.page_numbers:
            page_furniture_ids[pn].append(cand.candidate_id)
            page_furniture_fraction[pn] += area

    # Clamp fractions to [0, 1]
    for pn in page_furniture_fraction:
        page_furniture_fraction[pn] = min(1.0, page_furniture_fraction[pn])

    for tpl in profile.templates:
        for pn in tpl.page_numbers:
            page_template_id[pn] = tpl.template_id

    return dict(page_furniture_ids), page_template_id, dict(page_furniture_fraction)


# ---------------------------------------------------------------------------
# Internal types and helpers
# ---------------------------------------------------------------------------


class _PrimitiveOccurrence:
    """Lightweight record of a primitive's occurrence on a page."""

    __slots__ = (
        "bbox_norm",
        "content_hash",
        "is_decorative",
        "kind",
        "page_number",
        "primitive_id",
        "text_sample",
    )

    def __init__(
        self,
        *,
        page_number: int,
        primitive_id: str,
        kind: Literal["text", "image", "drawing"],
        bbox_norm: NormalizedBBox,
        text_sample: str = "",
        content_hash: str = "",
        is_decorative: bool = False,
    ) -> None:
        self.page_number = page_number
        self.primitive_id = primitive_id
        self.kind = kind
        self.bbox_norm = bbox_norm
        self.text_sample = text_sample
        self.content_hash = content_hash
        self.is_decorative = is_decorative


def _round_coord(v: float, tolerance: float) -> float:
    """Round a coordinate to the nearest tolerance step."""
    if tolerance <= 0:
        return v
    return round(v / tolerance) * tolerance


def _fingerprint_text(
    prim: TextPrimitiveEvidence, page_number: int, tolerance: float
) -> tuple[str, _PrimitiveOccurrence]:
    """Fingerprint a text primitive for clustering.

    For page numbers, we cluster by position + font only (text varies).
    For other repeated text, we include a text hash.
    """
    bbox = prim.bbox_norm
    rounded = (
        _round_coord(bbox.x0, tolerance),
        _round_coord(bbox.y0, tolerance),
        _round_coord(bbox.x1, tolerance),
        _round_coord(bbox.y1, tolerance),
    )
    font_key = f"{prim.font_name}:{prim.font_size:.1f}"

    # Page numbers: position + font cluster (text content varies)
    if _PAGE_NUMBER_RE.match(prim.text.strip()):
        key = f"text:pagenum:{rounded}:{font_key}"
    else:
        text_hash = hash_string(prim.text.strip())[:12]
        key = f"text:{rounded}:{font_key}:{text_hash}"

    occ = _PrimitiveOccurrence(
        page_number=page_number,
        primitive_id=prim.primitive_id,
        kind="text",
        bbox_norm=bbox,
        text_sample=prim.text[:80],
    )
    return key, occ


def _fingerprint_image(
    prim: ImagePrimitiveEvidence, page_number: int, tolerance: float
) -> tuple[str, _PrimitiveOccurrence]:
    bbox = prim.bbox_norm
    rounded = (
        _round_coord(bbox.x0, tolerance),
        _round_coord(bbox.y0, tolerance),
        _round_coord(bbox.x1, tolerance),
        _round_coord(bbox.y1, tolerance),
    )
    key = f"image:{rounded}:{prim.content_hash[:16]}"
    occ = _PrimitiveOccurrence(
        page_number=page_number,
        primitive_id=prim.primitive_id,
        kind="image",
        bbox_norm=bbox,
        content_hash=prim.content_hash,
    )
    return key, occ


def _fingerprint_drawing(
    prim: DrawingPrimitiveEvidence, page_number: int, tolerance: float
) -> tuple[str, _PrimitiveOccurrence]:
    bbox = prim.bbox_norm
    rounded = (
        _round_coord(bbox.x0, tolerance),
        _round_coord(bbox.y0, tolerance),
        _round_coord(bbox.x1, tolerance),
        _round_coord(bbox.y1, tolerance),
    )
    key = f"drawing:{rounded}:{prim.path_count}:{prim.is_decorative}"
    occ = _PrimitiveOccurrence(
        page_number=page_number,
        primitive_id=prim.primitive_id,
        kind="drawing",
        bbox_norm=bbox,
        is_decorative=prim.is_decorative,
    )
    return key, occ


def _build_clusters(
    primitives: list[PrimitivePageEvidence],
    tolerance: float,
) -> dict[str, list[_PrimitiveOccurrence]]:
    """Fingerprint all primitives and group into cross-page clusters."""
    clusters: dict[str, list[_PrimitiveOccurrence]] = defaultdict(list)

    for page in primitives:
        pn = page.page_number
        for tp in page.text_primitives:
            key, occ = _fingerprint_text(tp, pn, tolerance)
            clusters[key].append(occ)
        for ip in page.image_primitives:
            key, occ = _fingerprint_image(ip, pn, tolerance)
            clusters[key].append(occ)
        for dp in page.drawing_primitives:
            key, occ = _fingerprint_drawing(dp, pn, tolerance)
            clusters[key].append(occ)

    return clusters


def _median_bbox(cluster: list[_PrimitiveOccurrence]) -> NormalizedBBox:
    """Compute the median bounding box across occurrences."""
    x0s = [occ.bbox_norm.x0 for occ in cluster]
    y0s = [occ.bbox_norm.y0 for occ in cluster]
    x1s = [occ.bbox_norm.x1 for occ in cluster]
    y1s = [occ.bbox_norm.y1 for occ in cluster]

    return NormalizedBBox(
        x0=min(1.0, max(0.0, median(x0s))),
        y0=min(1.0, max(0.0, median(y0s))),
        x1=min(1.0, max(0.0, median(x1s))),
        y1=min(1.0, max(0.0, median(y1s))),
    )


def _bbox_area(bbox: NormalizedBBox) -> float:
    """Area of a normalized bbox (in [0, 1] page-fraction)."""
    w = max(0.0, bbox.x1 - bbox.x0)
    h = max(0.0, bbox.y1 - bbox.y0)
    return w * h


def _is_near_edge(bbox: NormalizedBBox, margin: float) -> bool:
    """Check if a bbox is within margin of any page edge."""
    return bbox.y0 < margin or bbox.y1 > 1.0 - margin or bbox.x0 < margin or bbox.x1 > 1.0 - margin


def _passes_furniture_gates(
    representative: _PrimitiveOccurrence,
    median_bbox: NormalizedBBox,
    edge_margin: float,
) -> bool:
    """Apply classification gates to determine if a cluster is furniture.

    A repeated cluster is furniture if:
    - It's near a page edge, OR
    - It's a decorative drawing, OR
    - It matches the page-number pattern
    """
    if _is_near_edge(median_bbox, edge_margin):
        return True
    if representative.is_decorative:
        return True
    return representative.kind == "text" and bool(
        _PAGE_NUMBER_RE.match(representative.text_sample.strip())
    )


def _classify_furniture_type(
    representative: _PrimitiveOccurrence,
    median_bbox: NormalizedBBox,
    edge_margin: float,
) -> FurnitureType:
    """Classify a furniture cluster by type based on position and content."""
    is_top = median_bbox.y0 < edge_margin
    is_bottom = median_bbox.y1 > 1.0 - edge_margin
    is_text = representative.kind == "text"
    is_drawing = representative.kind == "drawing"

    # Page numbers: bottom-zone text matching number pattern
    if is_text and is_bottom and _PAGE_NUMBER_RE.match(representative.text_sample.strip()):
        return "page_number"

    # Top-zone text is a header
    if is_text and is_top:
        return "header"

    # Bottom-zone text is a footer
    if is_text and is_bottom:
        return "footer"

    # Decorative drawings
    if is_drawing and representative.is_decorative:
        area = _bbox_area(median_bbox)
        if area > 0.3:
            return "border"
        return "ornament"

    # Edge drawings without decorative flag
    if is_drawing:
        width = median_bbox.x1 - median_bbox.x0
        height = median_bbox.y1 - median_bbox.y0
        if width > 0.5 and height < 0.02:
            return "divider"
        return "border"

    # Edge images (only remaining kind)
    area = _bbox_area(median_bbox)
    if area > 0.3:
        return "background_panel"
    return "ornament"


def _assign_templates(
    candidates: list[FurnitureCandidate],
) -> list[TemplateAssignment]:
    """Group pages into templates by their furniture sets."""
    if not candidates:
        return []

    # Build page -> set of furniture ids
    page_furn_set: dict[int, frozenset[str]] = defaultdict(frozenset)
    for cand in candidates:
        for pn in cand.page_numbers:
            page_furn_set[pn] = page_furn_set[pn] | {cand.candidate_id}

    # Group pages by identical furniture sets (use actual page numbers, not range)
    set_to_pages: dict[frozenset[str], list[int]] = defaultdict(list)
    for pn, fset in page_furn_set.items():
        if fset:
            set_to_pages[fset].append(pn)

    templates: list[TemplateAssignment] = []
    for fset, pages in set_to_pages.items():
        sorted_ids = sorted(fset)
        tpl_id = f"tpl:{hash_string(':'.join(sorted_ids))[:8]}"
        templates.append(
            TemplateAssignment(
                template_id=tpl_id,
                page_numbers=sorted(pages),
                furniture_ids=sorted_ids,
            )
        )

    return sorted(templates, key=lambda t: t.page_numbers[0] if t.page_numbers else 0)
