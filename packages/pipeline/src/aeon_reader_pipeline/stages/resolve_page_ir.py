"""Stage — resolve canonical evidence into page IR."""

from __future__ import annotations

from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    ResolvedPageIR,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.stages.confidence import route_page, score_page_confidence
from aeon_reader_pipeline.utils.page_filter import pages_to_process

STAGE_NAME = "resolve_page_ir"
STAGE_VERSION = "0.2.0"


def _canonical_filename(page_number: int) -> str:
    return f"evidence/p{page_number:04d}_canonical.json"


def _resolved_filename(page_number: int) -> str:
    return f"resolved/p{page_number:04d}.json"


@register_stage
class ResolvePageIRStage(BaseStage):
    """Resolve canonical evidence into page IR for semantic block building."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Build resolved page IR from canonical evidence"

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
        ctx.logger.info("resolving_page_ir", page_count=len(pages))

        for page_number in pages:
            canonical = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "collect_evidence",
                _canonical_filename(page_number),
                CanonicalPageEvidence,
            )

            confidence, reasons = score_page_confidence(canonical)
            render_mode = route_page(confidence)

            resolved = ResolvedPageIR(
                page_number=canonical.page_number,
                doc_id=canonical.doc_id,
                width_pt=canonical.width_pt,
                height_pt=canonical.height_pt,
                canonical_evidence_hash=hash_model(canonical),
                render_mode=render_mode,
                page_confidence=confidence,
                confidence_reasons=reasons,
            )

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                _resolved_filename(page_number),
                resolved,
            )

            ctx.logger.debug(
                "page_ir_resolved",
                page=page_number,
                render_mode=resolved.render_mode,
                confidence=round(confidence, 3),
            )

        ctx.logger.info("resolve_page_ir_complete", pages=len(pages))
