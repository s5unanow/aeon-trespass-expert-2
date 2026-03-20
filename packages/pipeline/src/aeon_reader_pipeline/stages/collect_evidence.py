"""Stage — collect primitive evidence into canonical page evidence."""

from __future__ import annotations

from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    PrimitivePageEvidence,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.furniture_detection import (
    compute_page_furniture,
    detect_furniture,
)
from aeon_reader_pipeline.utils.page_filter import pages_to_process
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions
from aeon_reader_pipeline.utils.reading_order import compute_reading_order

STAGE_NAME = "collect_evidence"
STAGE_VERSION = "0.4.0"


def _primitive_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_primitive.json"


def _canonical_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_canonical.json"


def _regions_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_regions.json"


def _reading_order_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_reading_order.json"


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

        # Pass 1: Load all primitive evidence
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

        # Build per-page lookups
        page_furn_ids, page_tpl_id, page_furn_frac = compute_page_furniture(
            furniture_profile,
        )

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

            # Estimate column count as max columns in any single band
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
                has_tables=len(primitive.table_primitives) > 0,
                has_figures=len(primitive.image_primitives) > 0,
                has_callouts=False,
                furniture_fraction=page_furn_frac.get(pn, 0.0),
                furniture_ids=furn_ids,
                template_id=page_tpl_id.get(pn, ""),
                region_graph=region_graph,
                reading_order=reading_order,
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
