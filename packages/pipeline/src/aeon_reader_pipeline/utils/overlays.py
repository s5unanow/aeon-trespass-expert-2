"""Debug overlay renderers for evidence artifacts.

Each function takes evidence models + a PyMuPDF page, draws color-coded
annotations, and returns PNG bytes. Used by the ``generate-overlays``
CLI command for operator debugging of hard pages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pymupdf

if TYPE_CHECKING:
    from aeon_reader_pipeline.models.evidence_models import (
        DocumentAssetRegistry,
        DocumentFurnitureProfile,
        FigureCaptionLink,
        NormalizedBBox,
        PageReadingOrder,
        PageRegionGraph,
        PageSymbolCandidates,
        PrimitivePageEvidence,
        ResolvedPageIR,
    )

# ---------------------------------------------------------------------------
# Color constants (R, G, B) — 0-1 float tuples for PyMuPDF
# ---------------------------------------------------------------------------

# Primitives
_CLR_TEXT = pymupdf.pdfcolor["blue"]
_CLR_IMAGE = (1.0, 0.35, 0.0)  # red-orange
_CLR_TABLE = pymupdf.pdfcolor["green"]
_CLR_DRAWING = pymupdf.pdfcolor["purple"]

# Regions
_REGION_COLORS: dict[str, tuple[float, float, float]] = {
    "main_flow": (0.4, 0.7, 1.0),
    "column": (0.2, 0.4, 1.0),
    "band": (0.3, 0.6, 0.9),
    "sidebar": (1.0, 0.6, 0.0),
    "callout": (1.0, 0.9, 0.0),
    "figure": (1.0, 0.0, 0.0),
    "table": (0.0, 0.8, 0.0),
    "caption": (0.6, 0.4, 0.2),
    "decoration": (0.5, 0.5, 0.5),
    "furniture": (0.5, 0.5, 0.5),
    "unknown": (0.8, 0.0, 0.8),
}

# Flow roles (reading order)
_FLOW_COLORS: dict[str, tuple[float, float, float]] = {
    "main": (0.2, 0.4, 1.0),
    "aside": (1.0, 0.6, 0.0),
    "interruption": (1.0, 0.0, 0.0),
}

# Symbols
_CLR_SYM_HIGH = (0.0, 0.8, 0.0)
_CLR_SYM_MED = (1.0, 0.75, 0.0)
_CLR_SYM_LOW = (1.0, 0.0, 0.0)
_CLR_SYM_UNCLASSIFIED = (0.8, 0.0, 0.8)
_CLR_SYM_DECORATIVE = (0.5, 0.5, 0.5)

# Furniture
_CLR_FURNITURE = (1.0, 0.9, 0.0)

# Confidence
_CLR_CONF_HIGH = (0.0, 0.8, 0.0, 0.15)
_CLR_CONF_MED = (1.0, 0.75, 0.0, 0.15)
_CLR_CONF_LOW = (1.0, 0.0, 0.0, 0.15)

# Label
_LABEL_FONT_SIZE = 7
_LABEL_BG = (1.0, 1.0, 1.0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm_to_rect(bbox: NormalizedBBox, width_pt: float, height_pt: float) -> pymupdf.Rect:
    """Convert a NormalizedBBox to a PyMuPDF Rect in page points."""
    return pymupdf.Rect(
        bbox.x0 * width_pt,
        bbox.y0 * height_pt,
        bbox.x1 * width_pt,
        bbox.y1 * height_pt,
    )


def _draw_label(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    color: tuple[float, float, float],
) -> None:
    """Draw a small text label at the top-left of a rect."""
    label_pt = pymupdf.Point(rect.x0 + 1, rect.y0 + _LABEL_FONT_SIZE + 1)
    # Background rect for readability
    tw = len(text) * _LABEL_FONT_SIZE * 0.55
    th = _LABEL_FONT_SIZE + 2
    bg_rect = pymupdf.Rect(label_pt.x - 1, label_pt.y - th, label_pt.x + tw + 1, label_pt.y + 1)
    page.draw_rect(bg_rect, color=None, fill=_LABEL_BG, fill_opacity=0.8)
    page.insert_text(label_pt, text, fontsize=_LABEL_FONT_SIZE, color=color)


def _render_page(page: pymupdf.Page, dpi: int) -> bytes:
    """Render a page to PNG bytes."""
    pix = page.get_pixmap(dpi=dpi)
    return bytes(pix.tobytes("png"))


# ---------------------------------------------------------------------------
# Overlay renderers
# ---------------------------------------------------------------------------


def render_primitives_overlay(
    page: pymupdf.Page,
    evidence: PrimitivePageEvidence,
    dpi: int = 150,
) -> bytes:
    """Render primitives: text=blue, image=orange, table=green, drawing=purple."""
    w, h = evidence.width_pt, evidence.height_pt

    for tp in evidence.text_primitives:
        rect = _norm_to_rect(tp.bbox_norm, w, h)
        page.draw_rect(rect, color=_CLR_TEXT, width=0.5, fill=_CLR_TEXT, fill_opacity=0.08)
        label = f"T:{tp.primitive_id.split(':')[-1]}"
        _draw_label(page, rect, label, _CLR_TEXT)

    for ip in evidence.image_primitives:
        rect = _norm_to_rect(ip.bbox_norm, w, h)
        page.draw_rect(rect, color=_CLR_IMAGE, width=0.8, fill=_CLR_IMAGE, fill_opacity=0.12)
        label = f"I:{ip.primitive_id.split(':')[-1]}"
        _draw_label(page, rect, label, _CLR_IMAGE)

    for tbl in evidence.table_primitives:
        rect = _norm_to_rect(tbl.bbox_norm, w, h)
        page.draw_rect(rect, color=_CLR_TABLE, width=0.8, fill=_CLR_TABLE, fill_opacity=0.1)
        label = f"Tbl:{tbl.rows}x{tbl.cols}"
        _draw_label(page, rect, label, _CLR_TABLE)

    for dp in evidence.drawing_primitives:
        rect = _norm_to_rect(dp.bbox_norm, w, h)
        page.draw_rect(rect, color=_CLR_DRAWING, width=0.5, fill=_CLR_DRAWING, fill_opacity=0.08)
        label = f"D:{dp.primitive_id.split(':')[-1]}"
        _draw_label(page, rect, label, _CLR_DRAWING)

    return _render_page(page, dpi)


def render_furniture_overlay(
    page: pymupdf.Page,
    furniture_profile: DocumentFurnitureProfile,
    page_number: int,
    dpi: int = 150,
) -> bytes:
    """Render furniture candidates that appear on the given page as yellow dashed outlines."""
    for cand in furniture_profile.furniture_candidates:
        if page_number not in cand.page_numbers:
            continue
        # Use page mediabox dimensions
        w = page.rect.width
        h = page.rect.height
        rect = _norm_to_rect(cand.bbox_norm, w, h)
        page.draw_rect(
            rect,
            color=_CLR_FURNITURE,
            width=1.0,
            dashes="[3 2]",
            fill=_CLR_FURNITURE,
            fill_opacity=0.06,
        )
        label = f"F:{cand.furniture_type}"
        _draw_label(page, rect, label, _CLR_FURNITURE)

    return _render_page(page, dpi)


def render_regions_overlay(
    page: pymupdf.Page,
    region_graph: PageRegionGraph,
    dpi: int = 150,
) -> bytes:
    """Render region segmentation with color-coded region kinds."""
    w, h = region_graph.width_pt, region_graph.height_pt

    for region in region_graph.regions:
        color = _REGION_COLORS.get(region.kind_hint, (0.5, 0.5, 0.5))
        rect = _norm_to_rect(region.bbox, w, h)
        page.draw_rect(rect, color=color, width=0.8, fill=color, fill_opacity=0.12)
        conf = region.confidence.value
        label = f"{region.kind_hint}:{conf:.0%}"
        _draw_label(page, rect, label, color)

    return _render_page(page, dpi)


def render_reading_order_overlay(
    page: pymupdf.Page,
    region_graph: PageRegionGraph,
    reading_order: PageReadingOrder,
    dpi: int = 150,
) -> bytes:
    """Render reading order: numbered circles at region centroids with flow-colored arrows."""
    w, h = region_graph.width_pt, region_graph.height_pt

    # Build region lookup
    region_map = {r.region_id: r for r in region_graph.regions}

    centroids: list[pymupdf.Point] = []
    entries = sorted(reading_order.entries, key=lambda e: e.sequence_index)

    for entry in entries:
        region = region_map.get(entry.region_id)
        if region is None:
            continue
        rect = _norm_to_rect(region.bbox, w, h)
        cx = (rect.x0 + rect.x1) / 2
        cy = (rect.y0 + rect.y1) / 2
        center = pymupdf.Point(cx, cy)
        centroids.append(center)

        color = _FLOW_COLORS.get(entry.flow_role, (0.5, 0.5, 0.5))

        # Draw region outline lightly
        page.draw_rect(rect, color=color, width=0.4, fill=color, fill_opacity=0.06)

        # Draw numbered circle
        page.draw_circle(center, 8, color=color, fill=_LABEL_BG, fill_opacity=0.9, width=1.0)
        num_text = str(entry.sequence_index)
        text_pt = pymupdf.Point(cx - len(num_text) * 2.5, cy + 3)
        page.insert_text(text_pt, num_text, fontsize=7, color=color)

    # Draw arrows between sequential entries
    for i in range(len(centroids) - 1):
        p1 = centroids[i]
        p2 = centroids[i + 1]
        entry = entries[i + 1]
        color = _FLOW_COLORS.get(entry.flow_role, (0.5, 0.5, 0.5))
        page.draw_line(p1, p2, color=color, width=0.6, dashes="[2 1]")

    return _render_page(page, dpi)


def render_assets_overlay(
    page: pymupdf.Page,
    asset_registry: DocumentAssetRegistry,
    page_number: int,
    dpi: int = 150,
) -> bytes:
    """Render asset occurrences on the given page."""
    w = page.rect.width
    h = page.rect.height

    for asset_cls in asset_registry.asset_classes:
        for occ in asset_cls.occurrences:
            if occ.page_number != page_number:
                continue
            # Color by asset kind
            if asset_cls.is_furniture:
                color = _CLR_SYM_DECORATIVE
            elif asset_cls.kind == "raster":
                color = _CLR_IMAGE
            elif asset_cls.kind == "vector_cluster":
                color = _CLR_DRAWING
            else:
                color = (0.5, 0.5, 0.5)

            rect = _norm_to_rect(occ.bbox_norm, w, h)
            page.draw_rect(rect, color=color, width=0.8, fill=color, fill_opacity=0.1)
            label = f"{asset_cls.kind}:{occ.context_hint}"
            _draw_label(page, rect, label, color)

    return _render_page(page, dpi)


def render_symbols_overlay(
    page: pymupdf.Page,
    symbol_candidates: PageSymbolCandidates,
    dpi: int = 150,
) -> bytes:
    """Render symbol candidates with confidence-based colors."""
    w = page.rect.width
    h = page.rect.height

    for cand in symbol_candidates.candidates:
        if cand.is_decorative:
            color = _CLR_SYM_DECORATIVE
            style = "[3 2]"
        elif not cand.is_classified:
            color = _CLR_SYM_UNCLASSIFIED
            style = ""
        elif cand.confidence >= 0.8:
            color = _CLR_SYM_HIGH
            style = ""
        elif cand.confidence >= 0.5:
            color = _CLR_SYM_MED
            style = ""
        else:
            color = _CLR_SYM_LOW
            style = ""

        rect = _norm_to_rect(cand.bbox_norm, w, h)
        page.draw_rect(
            rect,
            color=color,
            width=0.8 if style == "" else 0.6,
            dashes=style if style else None,
            fill=color,
            fill_opacity=0.1,
        )
        label = cand.symbol_id if cand.symbol_id else "?"
        _draw_label(page, rect, label, color)

    return _render_page(page, dpi)


def render_figure_caption_overlay(
    page: pymupdf.Page,
    region_graph: PageRegionGraph,
    links: list[FigureCaptionLink],
    dpi: int = 150,
) -> bytes:
    """Render figure-caption links as connected pairs."""
    w, h = region_graph.width_pt, region_graph.height_pt
    region_map = {r.region_id: r for r in region_graph.regions}

    for link in links:
        fig_region = region_map.get(link.figure_id)
        cap_region = region_map.get(link.caption_id)

        # Draw figure rect in red
        if fig_region is not None:
            fig_rect = _norm_to_rect(fig_region.bbox, w, h)
            page.draw_rect(
                fig_rect, color=(1.0, 0.0, 0.0), width=1.0, fill=(1.0, 0.0, 0.0), fill_opacity=0.1
            )
            _draw_label(page, fig_rect, f"fig:{link.score:.0%}", (1.0, 0.0, 0.0))

        # Draw caption rect in green
        if cap_region is not None:
            cap_rect = _norm_to_rect(cap_region.bbox, w, h)
            page.draw_rect(cap_rect, color=_CLR_TABLE, width=1.0, fill=_CLR_TABLE, fill_opacity=0.1)
            _draw_label(page, cap_rect, "caption", _CLR_TABLE)

        # Draw connecting line
        if fig_region is not None and cap_region is not None:
            fig_center = pymupdf.Point(
                (fig_rect.x0 + fig_rect.x1) / 2,
                (fig_rect.y0 + fig_rect.y1) / 2,
            )
            cap_center = pymupdf.Point(
                (cap_rect.x0 + cap_rect.x1) / 2,
                (cap_rect.y0 + cap_rect.y1) / 2,
            )
            page.draw_line(fig_center, cap_center, color=(0.0, 0.5, 0.0), width=1.0)

    return _render_page(page, dpi)


def render_confidence_overlay(
    page: pymupdf.Page,
    resolved: ResolvedPageIR,
    dpi: int = 150,
) -> bytes:
    """Render a full-page confidence color wash with a text banner."""
    conf = resolved.page_confidence

    if conf >= 0.8:
        fill_color = _CLR_CONF_HIGH
        label = "HIGH"
    elif conf >= 0.5:
        fill_color = _CLR_CONF_MED
        label = "MEDIUM"
    else:
        fill_color = _CLR_CONF_LOW
        label = "LOW"

    # Full-page wash
    page.draw_rect(
        page.rect,
        color=None,
        fill=fill_color[:3],
        fill_opacity=fill_color[3],
    )

    # Banner at top
    banner_text = f"Confidence: {conf:.0%} ({label}) | Mode: {resolved.render_mode}"
    if resolved.confidence_reasons:
        banner_text += f" | {', '.join(resolved.confidence_reasons[:3])}"

    banner_rect = pymupdf.Rect(0, 0, page.rect.width, 16)
    page.draw_rect(banner_rect, color=None, fill=fill_color[:3], fill_opacity=0.7)
    page.insert_text(pymupdf.Point(4, 12), banner_text, fontsize=8, color=(0.0, 0.0, 0.0))

    return _render_page(page, dpi)
