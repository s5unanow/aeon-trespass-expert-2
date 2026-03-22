"""Stage — collect primitive evidence into canonical page evidence."""

from __future__ import annotations

from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    PageSymbolCandidates,
    PrimitivePageEvidence,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.asset_registry import (
    build_asset_registry,
    compute_page_assets,
)
from aeon_reader_pipeline.utils.furniture_detection import (
    compute_page_furniture,
    detect_furniture,
)
from aeon_reader_pipeline.utils.page_filter import pages_to_process
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions
from aeon_reader_pipeline.utils.reading_order import compute_reading_order
from aeon_reader_pipeline.utils.symbol_candidates import (
    build_symbol_summary,
    compute_page_symbol_ids,
    generate_page_candidates,
)

STAGE_NAME = "collect_evidence"
STAGE_VERSION = "0.5.0"


def _primitive_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_primitive.json"


def _canonical_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_canonical.json"


def _regions_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_regions.json"


def _reading_order_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_reading_order.json"


def _symbol_candidates_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_symbol_candidates.json"


@register_stage
class CollectEvidenceStage(BaseStage):
    """Collect primitive evidence into canonical page evidence."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Build canonical page evidence from primitive evidence"

    def should_skip(self, ctx: StageContext) -> bool:
        if ctx.pipeline_config.architecture == "v2":
            return True
        return super().should_skip(ctx)

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        pages = pages_to_process(manifest.page_count, ctx.pipeline_config.page_filter)
        ctx.logger.info("collecting_evidence", page_count=len(pages))

        # Pass 1: Load all primitive evidence and persist for downstream stages
        all_primitives: list[PrimitivePageEvidence] = []
        for page_number in pages:
            primitive = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "extract_primitives",
                _primitive_filename(page_number),
                PrimitivePageEvidence,
            )
            all_primitives.append(primitive)
            # Persist primitive evidence in this stage's directory so downstream
            # v3 stages (e.g. resolve_assets_symbols) can read it.
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _primitive_filename(page_number),
                primitive,
            )

        # Cross-page furniture detection
        furniture_profile = detect_furniture(all_primitives)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "evidence/furniture_profile.json",
            furniture_profile,
        )
        ctx.logger.info(
            "furniture_detected",
            candidates=len(furniture_profile.furniture_candidates),
            templates=len(furniture_profile.templates),
        )

        # Cross-page asset registry (S5U-257)
        asset_registry = build_asset_registry(all_primitives, furniture_profile)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "evidence/asset_registry.json",
            asset_registry,
        )
        ctx.logger.info(
            "asset_registry_built",
            asset_classes=len(asset_registry.asset_classes),
            total_occurrences=asset_registry.total_occurrences,
        )

        # Symbol candidate detection (S5U-258)
        all_page_candidates: list[PageSymbolCandidates] = []
        for prim in all_primitives:
            page_cands = generate_page_candidates(prim, asset_registry, ctx.symbol_pack)
            all_page_candidates.append(page_cands)
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _symbol_candidates_filename(prim.page_number),
                page_cands,
            )

        symbol_summary = build_symbol_summary(all_page_candidates, ctx.doc_id)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "evidence/symbol_summary.json",
            symbol_summary,
        )
        ctx.logger.info(
            "symbol_candidates_detected",
            total=symbol_summary.total_candidates,
            classified=symbol_summary.classified_count,
            unclassified=symbol_summary.unclassified_count,
        )

        # Build per-page lookups
        page_furn_ids, page_tpl_id, page_furn_frac = compute_page_furniture(
            furniture_profile,
        )
        page_asset_occ_ids = compute_page_assets(asset_registry)
        page_sym_ids = compute_page_symbol_ids(all_page_candidates)

        # Pass 2: Build region graphs and canonical evidence
        for primitive in all_primitives:
            pn = primitive.page_number
            furn_ids = page_furn_ids.get(pn, [])

            # Region segmentation (S5U-255)
            region_graph = segment_page_regions(primitive, furniture_profile, furn_ids)

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _regions_filename(pn),
                region_graph,
            )

            # Reading order reconstruction (S5U-256)
            reading_order = compute_reading_order(region_graph)

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _reading_order_filename(pn),
                reading_order,
            )

            # Derive summary flags from post-furniture region graph
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

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _canonical_filename(pn),
                canonical,
            )

            ctx.logger.debug(
                "canonical_evidence_built",
                page=pn,
                has_tables=canonical.has_tables,
                has_figures=canonical.has_figures,
                furniture_fraction=canonical.furniture_fraction,
                template_id=canonical.template_id,
                region_count=len(region_graph.regions),
                column_count=estimated_columns,
                reading_order_entries=len(reading_order.entries),
            )

        ctx.logger.info("collect_evidence_complete", pages=len(pages))
