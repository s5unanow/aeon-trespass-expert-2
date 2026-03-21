"""Reading-order reconstruction from a PageRegionGraph.

Linearises the region graph into a deterministic reading sequence:
  1. Bands are traversed top-to-bottom (by band_index).
  2. Within each band, columns are emitted left-to-right (by column_index).
  3. Figures, tables, and other non-text regions inside a band are emitted
     after columns at their vertical position.
  4. Sidebars and callouts are tagged as ``flow_role="aside"``.
  5. Full-width bands that interrupt a multi-column sequence are tagged
     as ``flow_role="interruption"``.

Pure functions — no IO or stage dependencies.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    FlowRole,
    PageReadingOrder,
    PageRegionGraph,
    ReadingOrderEntry,
    RegionCandidate,
    RegionConfidence,
    RegionKind,
)

# Region kinds that are emitted as asides rather than main flow
_ASIDE_KINDS: frozenset[RegionKind] = frozenset({"sidebar", "callout"})

# Region kinds for non-text content within a band
_INLINE_KINDS: frozenset[RegionKind] = frozenset({"figure", "table", "caption"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_interruption(band_pos: int, band_col_counts: list[int]) -> bool:
    """True when a single-column band truly interrupts a multi-column flow.

    A band is an interruption only if there is at least one multi-column
    band both before and after it in the band sequence.  Leading/trailing
    single-column bands are *not* interruptions.
    """
    if band_col_counts[band_pos] != 1 or len(band_col_counts) <= 1:
        return False
    has_multi_before = any(cc > 1 for cc in band_col_counts[:band_pos])
    has_multi_after = any(cc > 1 for cc in band_col_counts[band_pos + 1 :])
    return has_multi_before and has_multi_after


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_reading_order(graph: PageRegionGraph) -> PageReadingOrder:
    """Build a PageReadingOrder from a PageRegionGraph.

    Args:
        graph: The page's region segmentation graph.

    Returns:
        A PageReadingOrder with a deterministic entry sequence.
    """
    if not graph.regions:
        return PageReadingOrder(
            page_number=graph.page_number,
            doc_id=graph.doc_id,
            total_regions=0,
        )

    region_by_id = {r.region_id: r for r in graph.regions}

    # Separate top-level bands from child regions
    bands = sorted(
        (r for r in graph.regions if r.kind_hint == "band"),
        key=lambda r: r.band_index if r.band_index is not None else 0,
    )

    # Build parent→children map from containment edges
    children_of: dict[str, list[RegionCandidate]] = {}
    for edge in graph.edges:
        if edge.edge_type == "contains":
            child = region_by_id.get(edge.dst_region_id)
            if child is not None:
                children_of.setdefault(edge.src_region_id, []).append(child)

    # Precompute column counts per band for interruption detection
    band_col_counts = [int(b.features.get("column_count", 1)) for b in bands]

    entries: list[ReadingOrderEntry] = []
    assigned_ids: set[str] = set()
    seq = 0

    for band_pos, band in enumerate(bands):
        children = children_of.get(band.region_id, [])
        columns = sorted(
            (c for c in children if c.kind_hint == "column"),
            key=lambda c: c.column_index if c.column_index is not None else 0,
        )
        inlines = sorted(
            (c for c in children if c.kind_hint in _INLINE_KINDS),
            key=lambda c: c.bbox.y0,
        )
        asides = sorted(
            (c for c in children if c.kind_hint in _ASIDE_KINDS),
            key=lambda c: c.bbox.y0,
        )

        # Determine flow role: only true mid-sequence breaks are interruptions
        band_flow_role: FlowRole = (
            "interruption" if _is_interruption(band_pos, band_col_counts) else "main"
        )

        if columns:
            # Multi-column: emit columns left-to-right
            for col in columns:
                entry = ReadingOrderEntry(
                    sequence_index=seq,
                    region_id=col.region_id,
                    kind_hint=col.kind_hint,
                    flow_role="main",
                    band_index=col.band_index,
                    column_index=col.column_index,
                    confidence=col.confidence,
                )
                entries.append(entry)
                assigned_ids.add(col.region_id)
                seq += 1
        else:
            # Single-column band: emit the band itself
            entry = ReadingOrderEntry(
                sequence_index=seq,
                region_id=band.region_id,
                kind_hint=band.kind_hint,
                flow_role=band_flow_role,
                band_index=band.band_index,
                confidence=band.confidence,
            )
            entries.append(entry)
            assigned_ids.add(band.region_id)
            seq += 1

        # Emit inline content (figures, tables, captions)
        for inline_region in inlines:
            entry = ReadingOrderEntry(
                sequence_index=seq,
                region_id=inline_region.region_id,
                kind_hint=inline_region.kind_hint,
                flow_role="main",
                band_index=inline_region.band_index,
                confidence=inline_region.confidence,
            )
            entries.append(entry)
            assigned_ids.add(inline_region.region_id)
            seq += 1

        # Emit asides (sidebars, callouts)
        for aside_region in asides:
            entry = ReadingOrderEntry(
                sequence_index=seq,
                region_id=aside_region.region_id,
                kind_hint=aside_region.kind_hint,
                flow_role="aside",
                band_index=aside_region.band_index,
                confidence=RegionConfidence(
                    value=aside_region.confidence.value,
                    reasons=[*aside_region.confidence.reasons, "aside_placement"],
                ),
            )
            entries.append(entry)
            assigned_ids.add(aside_region.region_id)
            seq += 1

        # Mark bands with columns as assigned (they are structural, not content)
        if columns:
            assigned_ids.add(band.region_id)

    # Collect unassigned regions (e.g. orphan regions not in any band)
    all_ids = {r.region_id for r in graph.regions}
    unassigned = sorted(all_ids - assigned_ids)

    return PageReadingOrder(
        page_number=graph.page_number,
        doc_id=graph.doc_id,
        entries=entries,
        total_regions=len(graph.regions),
        unassigned_region_ids=unassigned,
    )
