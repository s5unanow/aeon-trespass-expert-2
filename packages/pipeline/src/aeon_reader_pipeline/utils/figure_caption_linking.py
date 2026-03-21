"""Figure-caption spatial linking from region graphs and primitive evidence.

Scores figure-caption pairs using x-overlap, y-distance, and exclusivity
to disambiguate multiple nearby figures/captions more reliably than
adjacency-only block-order heuristics.

Pure functions -- no IO or stage dependencies.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    FigureCaptionLink,
    NormalizedBBox,
    PageFigureCaptionLinks,
    PageRegionGraph,
    PrimitivePageEvidence,
    RegionCandidate,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.models.ir_models import (
    Block,
    CaptionBlock,
    FigureBlock,
    PageRecord,
    TextRun,
)
from aeon_reader_pipeline.utils.normalization import is_caption_text as _is_caption_text

# Scoring thresholds
_MAX_Y_DISTANCE = 0.30  # Max vertical gap (normalised) to consider linking
_MIN_LINK_SCORE = 0.10  # Discard pairs below this score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def link_figures_captions_spatial(
    region_graph: PageRegionGraph,
    primitive: PrimitivePageEvidence,
    record: PageRecord,
) -> PageFigureCaptionLinks:
    """Link figures to captions using spatial scoring from the region graph.

    Uses figure region bboxes and caption-like text primitive bboxes to
    score pairs by x-overlap and y-distance, then greedily assigns
    exclusive 1:1 links.

    Returns a ``PageFigureCaptionLinks`` artifact with scored links and
    block-level IDs resolved where possible.
    """
    figure_regions = [r for r in region_graph.regions if r.kind_hint == "figure"]
    caption_prims = [tp for tp in primitive.text_primitives if _is_caption_text(tp.text)]

    if not figure_regions or not caption_prims:
        return PageFigureCaptionLinks(
            page_number=region_graph.page_number,
            doc_id=region_graph.doc_id,
            method="spatial",
        )

    # Score all figure-caption pairs
    scored_pairs: list[tuple[float, FigureCaptionLink]] = []
    for fig in figure_regions:
        for cap in caption_prims:
            score, reasons = _score_pair(fig.bbox, cap.bbox_norm)
            if score >= _MIN_LINK_SCORE:
                scored_pairs.append(
                    (
                        score,
                        FigureCaptionLink(
                            figure_id=fig.region_id,
                            caption_id=cap.primitive_id,
                            score=score,
                            x_overlap_ratio=_x_overlap_ratio(fig.bbox, cap.bbox_norm),
                            y_distance_norm=abs(_y_distance(fig.bbox, cap.bbox_norm)),
                            reasons=reasons,
                        ),
                    )
                )

    # Greedy exclusive matching (highest score first)
    scored_pairs.sort(key=lambda x: x[0], reverse=True)
    used_figs: set[str] = set()
    used_caps: set[str] = set()
    links: list[FigureCaptionLink] = []

    for _score, link in scored_pairs:
        if link.figure_id in used_figs or link.caption_id in used_caps:
            continue
        links.append(link)
        used_figs.add(link.figure_id)
        used_caps.add(link.caption_id)

    # Resolve region/primitive IDs to block IDs
    _resolve_block_ids(links, figure_regions, caption_prims, record)

    return PageFigureCaptionLinks(
        page_number=region_graph.page_number,
        doc_id=region_graph.doc_id,
        links=links,
        method="spatial",
    )


def link_figures_captions_sequential(
    record: PageRecord,
) -> PageFigureCaptionLinks:
    """Link figures to captions using block-order proximity (v2 fallback).

    Looks up to 2 blocks ahead of each figure for the nearest caption.
    Returns links with confidence metadata.

    Note: block ordering depends on how normalize_layout adds blocks
    (images first, then text). This can misorder figures relative to
    captions. Use ``link_figures_captions_spatial`` for reliable linking.
    """
    links: list[FigureCaptionLink] = []
    blocks = record.blocks
    used_captions: set[str] = set()

    for i, block in enumerate(blocks):
        if not isinstance(block, FigureBlock):
            continue
        for j in range(i + 1, min(i + 3, len(blocks))):
            candidate = blocks[j]
            if isinstance(candidate, CaptionBlock) and candidate.block_id not in used_captions:
                block_distance = j - i
                score = max(0.5, 1.0 - block_distance * 0.2)
                links.append(
                    FigureCaptionLink(
                        figure_id=block.block_id,
                        caption_id=candidate.block_id,
                        figure_block_id=block.block_id,
                        caption_block_id=candidate.block_id,
                        score=score,
                        y_distance_norm=block_distance / max(len(blocks), 1),
                        reasons=[
                            "sequential_proximity",
                            f"block_distance={block_distance}",
                        ],
                    )
                )
                used_captions.add(candidate.block_id)
                break

    return PageFigureCaptionLinks(
        page_number=record.page_number,
        doc_id=record.doc_id,
        links=links,
        method="sequential",
    )


def apply_links_to_blocks(
    record: PageRecord,
    links: PageFigureCaptionLinks,
) -> PageRecord:
    """Apply figure-caption links to IR blocks.

    Sets ``FigureBlock.caption_block_id`` and ``CaptionBlock.parent_block_id``
    for every link that has resolved block IDs.

    Returns a new PageRecord with updated blocks.
    """
    fig_to_cap: dict[str, str] = {}
    cap_to_fig: dict[str, str] = {}
    for link in links.links:
        if link.figure_block_id and link.caption_block_id:
            fig_to_cap[link.figure_block_id] = link.caption_block_id
            cap_to_fig[link.caption_block_id] = link.figure_block_id

    if not fig_to_cap:
        return record

    new_blocks: list[Block] = []
    for block in record.blocks:
        if isinstance(block, FigureBlock) and block.block_id in fig_to_cap:
            block = block.model_copy(update={"caption_block_id": fig_to_cap[block.block_id]})
        elif isinstance(block, CaptionBlock) and block.block_id in cap_to_fig:
            block = block.model_copy(update={"parent_block_id": cap_to_fig[block.block_id]})
        new_blocks.append(block)

    return record.model_copy(update={"blocks": new_blocks})


# ---------------------------------------------------------------------------
# Spatial scoring
# ---------------------------------------------------------------------------


def _score_pair(
    fig_bbox: NormalizedBBox,
    cap_bbox: NormalizedBBox,
) -> tuple[float, list[str]]:
    """Score a figure-caption pair based on spatial features.

    Returns (score, reasons) where score is in [0, 1].
    """
    reasons: list[str] = []

    x_overlap = _x_overlap_ratio(fig_bbox, cap_bbox)
    y_dist = _y_distance(fig_bbox, cap_bbox)
    abs_y = abs(y_dist)

    # Too far apart vertically — reject
    if abs_y > _MAX_Y_DISTANCE:
        return 0.0, ["too_far_vertically"]

    # x-overlap score
    if x_overlap > 0.5:
        reasons.append(f"good_x_overlap={x_overlap:.2f}")
    elif x_overlap > 0.2:
        reasons.append(f"moderate_x_overlap={x_overlap:.2f}")
    else:
        reasons.append(f"low_x_overlap={x_overlap:.2f}")

    # y-distance score: prefer close, prefer caption below figure
    if y_dist >= 0:
        y_score = max(0.0, 1.0 - abs_y * 3)
        reasons.append(f"caption_below, y_dist={y_dist:.3f}")
    else:
        y_score = max(0.0, 0.8 - abs_y * 3)
        reasons.append(f"caption_above, y_dist={y_dist:.3f}")

    score = min(1.0, 0.6 * x_overlap + 0.4 * y_score)
    if score < _MIN_LINK_SCORE:
        return 0.0, reasons

    return score, reasons


def _x_overlap_ratio(a: NormalizedBBox, b: NormalizedBBox) -> float:
    """Horizontal overlap ratio relative to the narrower bbox."""
    overlap_x0 = max(a.x0, b.x0)
    overlap_x1 = min(a.x1, b.x1)
    overlap_w = max(0.0, overlap_x1 - overlap_x0)
    min_w = min(max(0.001, a.x1 - a.x0), max(0.001, b.x1 - b.x0))
    return overlap_w / min_w


def _y_distance(fig: NormalizedBBox, cap: NormalizedBBox) -> float:
    """Signed vertical distance: positive if caption center is below figure center."""
    fig_center_y = (fig.y0 + fig.y1) / 2
    cap_center_y = (cap.y0 + cap.y1) / 2
    return cap_center_y - fig_center_y


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_block_ids(
    links: list[FigureCaptionLink],
    figure_regions: list[RegionCandidate],
    caption_prims: list[TextPrimitiveEvidence],
    record: PageRecord,
) -> None:
    """Map region/primitive IDs back to IR block IDs (in-place)."""
    figure_blocks = [b for b in record.blocks if isinstance(b, FigureBlock)]
    caption_blocks = [b for b in record.blocks if isinstance(b, CaptionBlock)]

    # Build caption text → block_id lookup
    cap_text_to_block: dict[str, str] = {}
    for cb in caption_blocks:
        text = "".join(n.text for n in cb.content if isinstance(n, TextRun)).strip()
        if text:
            cap_text_to_block[text] = cb.block_id

    # Build figure region ordering for positional matching to FigureBlocks.
    # Both figure regions and FigureBlocks are derived from the same images
    # in roughly the same top-to-bottom order.
    fig_region_order = sorted(figure_regions, key=lambda r: (r.bbox.y0, r.bbox.x0))
    fig_block_order = sorted(
        figure_blocks,
        key=lambda b: b.source_block_index if b.source_block_index is not None else 0,
    )

    region_to_block: dict[str, str] = {}
    for reg, blk in zip(fig_region_order, fig_block_order, strict=False):
        region_to_block[reg.region_id] = blk.block_id

    for link in links:
        # Resolve figure block ID
        if not link.figure_block_id:
            link.figure_block_id = region_to_block.get(link.figure_id, "")

        # Resolve caption block ID by matching text content
        if not link.caption_block_id:
            cap_prim = next(
                (tp for tp in caption_prims if tp.primitive_id == link.caption_id),
                None,
            )
            if cap_prim:
                link.caption_block_id = cap_text_to_block.get(cap_prim.text.strip(), "")
