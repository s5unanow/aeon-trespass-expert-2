"""Evidence pipeline test helper — runs the full evidence pipeline as pure functions.

Replicates the logic of CollectEvidenceStage + ResolvePageIRStage using only
utility functions (no IO, no StageContext). Lives in tests/ to avoid import
boundary issues (can freely import stages.confidence).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.config_models import SymbolPack
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    DocumentAssetRegistry,
    DocumentFurnitureProfile,
    PageReadingOrder,
    PageRegionGraph,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    ResolvedPageIR,
)
from aeon_reader_pipeline.stages.confidence import route_page, score_page_confidence
from aeon_reader_pipeline.utils.asset_registry import (
    build_asset_registry,
    compute_page_assets,
)
from aeon_reader_pipeline.utils.furniture_detection import (
    compute_page_furniture,
    detect_furniture,
)
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions
from aeon_reader_pipeline.utils.reading_order import compute_reading_order
from aeon_reader_pipeline.utils.symbol_candidates import (
    compute_page_symbol_ids,
    generate_page_candidates,
)


@dataclass
class EvidenceResult:
    """All intermediate results from a full evidence pipeline run."""

    furniture_profile: DocumentFurnitureProfile
    asset_registry: DocumentAssetRegistry
    all_symbol_candidates: list[PageSymbolCandidates]

    # Per-page results keyed by page_number
    region_graphs: dict[int, PageRegionGraph] = field(default_factory=dict)
    reading_orders: dict[int, PageReadingOrder] = field(default_factory=dict)
    canonicals: dict[int, CanonicalPageEvidence] = field(default_factory=dict)
    confidences: dict[int, tuple[float, list[str]]] = field(default_factory=dict)
    routes: dict[int, str] = field(default_factory=dict)
    resolved: dict[int, ResolvedPageIR] = field(default_factory=dict)


def run_evidence_pipeline(
    pages: list[PrimitivePageEvidence],
    symbol_pack: SymbolPack | None = None,
) -> EvidenceResult:
    """Run the full evidence pipeline on synthetic pages.

    Replicates CollectEvidenceStage + ResolvePageIRStage logic using only
    utility functions. Returns all intermediate artifacts for assertion.
    """
    if symbol_pack is None:
        symbol_pack = SymbolPack(pack_id="test", version="0.0.0")

    # --- Cross-page passes (CollectEvidenceStage) ---
    furniture_profile = detect_furniture(pages)
    asset_registry = build_asset_registry(pages, furniture_profile)

    all_page_candidates: list[PageSymbolCandidates] = []
    for prim in pages:
        page_cands = generate_page_candidates(prim, asset_registry, symbol_pack)
        all_page_candidates.append(page_cands)

    # Per-page lookups
    page_furn_ids, page_tpl_id, page_furn_frac = compute_page_furniture(furniture_profile)
    page_asset_occ_ids = compute_page_assets(asset_registry)
    page_sym_ids = compute_page_symbol_ids(all_page_candidates)

    result = EvidenceResult(
        furniture_profile=furniture_profile,
        asset_registry=asset_registry,
        all_symbol_candidates=all_page_candidates,
    )

    # --- Per-page passes ---
    for primitive in pages:
        pn = primitive.page_number
        furn_ids = page_furn_ids.get(pn, [])

        # Region segmentation
        region_graph = segment_page_regions(primitive, furniture_profile, furn_ids)
        result.region_graphs[pn] = region_graph

        # Reading order
        reading_order = compute_reading_order(region_graph)
        result.reading_orders[pn] = reading_order

        # Derive summary flags
        region_kinds = {r.kind_hint for r in region_graph.regions}
        estimated_columns = max(
            (
                int(r.features.get("column_count", 1))
                for r in region_graph.regions
                if r.kind_hint == "band"
            ),
            default=1,
        )

        canonical = CanonicalPageEvidence(
            page_number=pn,
            doc_id=primitive.doc_id,
            width_pt=primitive.width_pt,
            height_pt=primitive.height_pt,
            primitive_evidence_hash=hash_model(primitive),
            estimated_column_count=estimated_columns,
            has_tables="table" in region_kinds,
            has_figures="figure" in region_kinds,
            has_callouts="callout" in region_kinds,
            furniture_fraction=page_furn_frac.get(pn, 0.0),
            furniture_ids=furn_ids,
            template_id=page_tpl_id.get(pn, ""),
            region_graph=region_graph,
            reading_order=reading_order,
            asset_occurrence_ids=page_asset_occ_ids.get(pn, []),
            symbol_candidate_ids=page_sym_ids.get(pn, []),
        )
        result.canonicals[pn] = canonical

        # Confidence scoring + routing (ResolvePageIRStage)
        confidence, reasons = score_page_confidence(canonical)
        render_mode = route_page(confidence)
        result.confidences[pn] = (confidence, reasons)
        result.routes[pn] = render_mode

        resolved = ResolvedPageIR(
            page_number=pn,
            doc_id=primitive.doc_id,
            width_pt=primitive.width_pt,
            height_pt=primitive.height_pt,
            canonical_evidence_hash=hash_model(canonical),
            render_mode=render_mode,
            page_confidence=confidence,
            confidence_reasons=reasons,
        )
        result.resolved[pn] = resolved

    return result
