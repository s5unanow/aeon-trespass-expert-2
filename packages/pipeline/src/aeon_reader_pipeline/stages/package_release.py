"""Stage 14 — package final release archive with version metadata.

The package stage does not decide acceptance — it enforces it.
If QA has not accepted the run, packaging records the rejection and skips
the release assembly.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.qa_models import QASummary
from aeon_reader_pipeline.models.release_models import (
    ReleaseDocEntry,
    ReleaseManifest,
)
from aeon_reader_pipeline.models.site_bundle_models import SiteBundleManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.ids import content_fingerprint

STAGE_NAME = "package_release"
STAGE_VERSION = "1.0.0"


def _generate_release_id(run_id: str, doc_id: str) -> str:
    """Generate a deterministic release ID from run and doc."""
    return f"rel-{content_fingerprint(f'{run_id}:{doc_id}')[:12]}"


@register_stage
class PackageReleaseStage(BaseStage):
    """Package accepted artifacts and record deployable release metadata."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Package release with acceptance gating"

    def execute(self, ctx: StageContext) -> None:
        # Read bundle manifest
        bundle_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{ctx.doc_id}/bundle_manifest.json",
            SiteBundleManifest,
        )

        # Read QA summary
        qa_accepted = True
        rejection_reasons: list[str] = []
        try:
            qa_summary = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "evaluate_qa",
                "summary.json",
                QASummary,
            )
            qa_accepted = qa_summary.accepted
            rejection_reasons = list(qa_summary.rejection_reasons)
        except FileNotFoundError:
            ctx.logger.warning("qa_summary_not_found_for_release")

        release_id = _generate_release_id(ctx.run_id, ctx.doc_id)

        ctx.logger.info(
            "packaging_release",
            release_id=release_id,
            qa_accepted=qa_accepted,
        )

        doc_entry = ReleaseDocEntry(
            doc_id=ctx.doc_id,
            page_count=bundle_manifest.page_count,
            qa_accepted=qa_accepted,
            translation_coverage=bundle_manifest.translation_coverage,
        )

        release_manifest = ReleaseManifest(
            release_id=release_id,
            run_id=ctx.run_id,
            documents=[doc_entry],
            total_documents=1,
            all_accepted=qa_accepted,
            rejection_reasons=rejection_reasons,
            stage_version=STAGE_VERSION,
        )

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "release_manifest.json",
            release_manifest,
        )

        if qa_accepted:
            ctx.logger.info(
                "release_packaged",
                release_id=release_id,
                documents=1,
            )
        else:
            ctx.logger.warning(
                "release_rejected",
                release_id=release_id,
                reasons=rejection_reasons,
            )
