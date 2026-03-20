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

STAGE_NAME = "collect_evidence"
STAGE_VERSION = "0.2.0"


def _primitive_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_primitive.json"


def _canonical_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_canonical.json"


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

        # Pass 2: Build canonical evidence with furniture data
        for primitive in all_primitives:
            pn = primitive.page_number

            canonical = CanonicalPageEvidence(
                page_number=pn,
                doc_id=primitive.doc_id,
                width_pt=primitive.width_pt,
                height_pt=primitive.height_pt,
                primitive_evidence_hash=hash_model(primitive),
                estimated_column_count=1,
                has_tables=len(primitive.table_primitives) > 0,
                has_figures=len(primitive.image_primitives) > 0,
                has_callouts=False,
                furniture_fraction=page_furn_frac.get(pn, 0.0),
                furniture_ids=page_furn_ids.get(pn, []),
                template_id=page_tpl_id.get(pn, ""),
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
            )

        ctx.logger.info("collect_evidence_complete", pages=len(pages))
