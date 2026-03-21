"""Cross-page asset registry construction.

Builds a document-wide catalog of visual assets (raster images, vector
clusters, unresolved visual regions) from primitive page evidence. Each
unique asset becomes an ``AssetClass``; each page-level appearance becomes
an ``AssetOccurrence``.

Pure functions — no IO or stage dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from aeon_reader_pipeline.models.evidence_models import (
    AssetClass,
    AssetOccurrence,
    DocumentAssetRegistry,
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    NormalizedBBox,
    OccurrenceContext,
    PrimitivePageEvidence,
)
from aeon_reader_pipeline.utils.ids import asset_class_id, asset_occurrence_id

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Images smaller than this (in normalized area) are likely inline icons
_INLINE_AREA_THRESHOLD = 0.01
# Images larger than this are likely figures
_FIGURE_AREA_THRESHOLD = 0.04


def build_asset_registry(
    primitives: list[PrimitivePageEvidence],
    furniture_profile: DocumentFurnitureProfile | None = None,
) -> DocumentAssetRegistry:
    """Build a document-level asset registry from all pages' primitive evidence.

    Args:
        primitives: All pages' primitive evidence (must share a doc_id).
        furniture_profile: Optional furniture profile for marking furniture assets.

    Returns:
        A DocumentAssetRegistry with deduplicated asset classes and occurrences.
    """
    if not primitives:
        return DocumentAssetRegistry(doc_id="", total_pages_analyzed=0)

    doc_id = primitives[0].doc_id
    furniture_hashes = _collect_furniture_hashes(furniture_profile)

    raster_groups = _group_rasters(primitives)
    vector_groups = _group_vectors(primitives)

    asset_classes = _build_raster_classes(raster_groups, furniture_hashes)
    asset_classes.extend(_build_vector_classes(vector_groups))

    total_occs = sum(ac.occurrence_count for ac in asset_classes)

    return DocumentAssetRegistry(
        doc_id=doc_id,
        total_pages_analyzed=len(primitives),
        asset_classes=asset_classes,
        total_occurrences=total_occs,
    )


def compute_page_assets(
    registry: DocumentAssetRegistry,
) -> dict[int, list[str]]:
    """Derive per-page asset occurrence ID lists from a DocumentAssetRegistry.

    Returns:
        Dict mapping page_number to list of occurrence IDs on that page.
    """
    page_occ_ids: dict[int, list[str]] = defaultdict(list)
    for ac in registry.asset_classes:
        for occ in ac.occurrences:
            page_occ_ids[occ.page_number].append(occ.occurrence_id)
    return dict(page_occ_ids)


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class _ImageOccurrence:
    """Lightweight record of an image occurrence on a page."""

    __slots__ = (
        "bbox_norm",
        "colorspace",
        "content_hash",
        "height_px",
        "page_number",
        "primitive_id",
        "width_px",
    )

    def __init__(
        self,
        *,
        page_number: int,
        primitive_id: str,
        bbox_norm: NormalizedBBox,
        content_hash: str,
        width_px: int,
        height_px: int,
        colorspace: str,
    ) -> None:
        self.page_number = page_number
        self.primitive_id = primitive_id
        self.bbox_norm = bbox_norm
        self.content_hash = content_hash
        self.width_px = width_px
        self.height_px = height_px
        self.colorspace = colorspace


class _DrawingOccurrence:
    """Lightweight record of a drawing occurrence on a page."""

    __slots__ = ("bbox_norm", "page_number", "path_count", "primitive_id")

    def __init__(
        self,
        *,
        page_number: int,
        primitive_id: str,
        bbox_norm: NormalizedBBox,
        path_count: int,
    ) -> None:
        self.page_number = page_number
        self.primitive_id = primitive_id
        self.bbox_norm = bbox_norm
        self.path_count = path_count


# ---------------------------------------------------------------------------
# Internal helpers — grouping
# ---------------------------------------------------------------------------


def _collect_furniture_hashes(
    profile: DocumentFurnitureProfile | None,
) -> set[str]:
    """Extract content hashes from furniture candidates."""
    if not profile:
        return set()
    return {c.content_hash for c in profile.furniture_candidates if c.content_hash}


def _group_rasters(
    primitives: list[PrimitivePageEvidence],
) -> dict[str, list[_ImageOccurrence]]:
    """Group image primitives by content hash across all pages."""
    groups: dict[str, list[_ImageOccurrence]] = defaultdict(list)
    for page in primitives:
        for img in page.image_primitives:
            groups[img.content_hash].append(
                _ImageOccurrence(
                    page_number=page.page_number,
                    primitive_id=img.primitive_id,
                    bbox_norm=img.bbox_norm,
                    content_hash=img.content_hash,
                    width_px=img.width_px,
                    height_px=img.height_px,
                    colorspace=img.colorspace,
                )
            )
    return groups


def _group_vectors(
    primitives: list[PrimitivePageEvidence],
) -> dict[str, list[_DrawingOccurrence]]:
    """Group non-decorative drawings by fingerprint across all pages."""
    groups: dict[str, list[_DrawingOccurrence]] = defaultdict(list)
    for page in primitives:
        for drw in page.drawing_primitives:
            if drw.is_decorative:
                continue
            key = _drawing_fingerprint(drw)
            groups[key].append(
                _DrawingOccurrence(
                    page_number=page.page_number,
                    primitive_id=drw.primitive_id,
                    bbox_norm=drw.bbox_norm,
                    path_count=drw.path_count,
                )
            )
    return groups


# ---------------------------------------------------------------------------
# Internal helpers — class building
# ---------------------------------------------------------------------------


_AnyOccurrence = _ImageOccurrence | _DrawingOccurrence


def _build_occurrences(
    class_id: str,
    occs: list[_ImageOccurrence] | list[_DrawingOccurrence],
    context_fn: Callable[[_AnyOccurrence], OccurrenceContext],
) -> list[AssetOccurrence]:
    """Build AssetOccurrence list with deterministic IDs."""
    result: list[AssetOccurrence] = []
    page_counter: dict[int, int] = defaultdict(int)
    for o in occs:
        idx = page_counter[o.page_number]
        page_counter[o.page_number] += 1
        result.append(
            AssetOccurrence(
                occurrence_id=asset_occurrence_id(class_id, o.page_number, idx),
                page_number=o.page_number,
                bbox_norm=o.bbox_norm,
                source_primitive_id=o.primitive_id,
                context_hint=context_fn(o),
            )
        )
    return result


def _make_raster_context_fn(
    is_furn: bool,
) -> Callable[[_AnyOccurrence], OccurrenceContext]:
    """Create a context-hint function for a raster group."""

    def _fn(o: _AnyOccurrence) -> OccurrenceContext:
        return _guess_raster_context(o.bbox_norm, is_furn)

    return _fn


def _build_raster_classes(
    groups: dict[str, list[_ImageOccurrence]],
    furniture_hashes: set[str],
) -> list[AssetClass]:
    """Build AssetClass entries for raster image groups."""
    classes: list[AssetClass] = []
    for idx, (content_hash, occs) in enumerate(sorted(groups.items())):
        class_id = asset_class_id("raster", idx)
        rep = occs[0]
        is_furn = content_hash in furniture_hashes
        occurrences = _build_occurrences(
            class_id,
            occs,
            _make_raster_context_fn(is_furn),
        )
        classes.append(
            AssetClass(
                asset_class_id=class_id,
                kind="raster",
                content_hash=content_hash,
                width_px=rep.width_px,
                height_px=rep.height_px,
                colorspace=rep.colorspace,
                occurrence_count=len(occurrences),
                page_numbers=sorted({o.page_number for o in occs}),
                occurrences=occurrences,
                is_furniture=is_furn,
            )
        )
    return classes


def _build_vector_classes(
    groups: dict[str, list[_DrawingOccurrence]],
) -> list[AssetClass]:
    """Build AssetClass entries for vector cluster groups."""
    classes: list[AssetClass] = []
    for idx, (_key, occs) in enumerate(sorted(groups.items())):
        class_id = asset_class_id("vector_cluster", idx)
        rep = occs[0]
        occurrences = _build_occurrences(class_id, occs, _vector_context_fn)
        classes.append(
            AssetClass(
                asset_class_id=class_id,
                kind="vector_cluster",
                path_count=rep.path_count,
                occurrence_count=len(occurrences),
                page_numbers=sorted({o.page_number for o in occs}),
                occurrences=occurrences,
            )
        )
    return classes


# ---------------------------------------------------------------------------
# Internal helpers — classification
# ---------------------------------------------------------------------------


def _vector_context_fn(_o: _AnyOccurrence) -> OccurrenceContext:
    """Default context hint for vector clusters."""
    return "unknown"


def _bbox_area(bbox: NormalizedBBox) -> float:
    w = max(0.0, bbox.x1 - bbox.x0)
    h = max(0.0, bbox.y1 - bbox.y0)
    return w * h


def _guess_raster_context(
    bbox: NormalizedBBox,
    is_furniture: bool,
) -> OccurrenceContext:
    """Heuristic context classification based on bbox size and furniture status."""
    if is_furniture:
        return "decoration"
    area = _bbox_area(bbox)
    if area < _INLINE_AREA_THRESHOLD:
        return "inline"
    if area >= _FIGURE_AREA_THRESHOLD:
        return "figure"
    return "unknown"


def _drawing_fingerprint(drw: DrawingPrimitiveEvidence) -> str:
    """Fingerprint a non-decorative drawing for cross-page grouping.

    Groups by path count and rounded bbox dimensions (not position,
    since the same icon may appear at different positions).
    """
    w = round(drw.bbox_norm.x1 - drw.bbox_norm.x0, 2)
    h = round(drw.bbox_norm.y1 - drw.bbox_norm.y0, 2)
    return f"vec:{drw.path_count}:{w}:{h}"
