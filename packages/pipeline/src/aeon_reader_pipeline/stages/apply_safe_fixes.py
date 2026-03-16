"""Stage 10 — apply safe automatic fixes for QA findings that can be auto-corrected.

V1 behavior: pass-through mode. Pages are copied from enrich_content to 10_fix
unchanged. No automatic mutations. Future versions may enable safe fixers
that revalidate touched pages before export.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "apply_safe_fixes"
STAGE_VERSION = "1.0.0"


@register_stage
class ApplySafeFixesStage(BaseStage):
    """Pass-through stage that copies enriched pages to the fix output.

    In v1, this stage does not mutate content. It exists to establish
    the stage boundary so that export_site_bundle always reads from
    10_fix/pages/**, even if no fixes are applied.
    """

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Copy enriched pages to fix output (v1 pass-through)"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        ctx.logger.info(
            "applying_safe_fixes",
            page_count=manifest.page_count,
            mode="pass-through",
        )

        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "enrich_content",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{page_num:04d}.json",
                record,
            )

        ctx.logger.info(
            "safe_fixes_complete",
            pages=manifest.page_count,
            fixes_applied=0,
        )
