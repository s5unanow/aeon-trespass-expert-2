"""Stage 12 — build the static reader application from the site bundle.

This stage wraps the frontend build process. In v1 it records a build manifest
and validates that the exported bundle exists. The actual pnpm build is deferred
to EP-009 when the reader app is implemented.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.site_bundle_models import SiteBundleManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "build_reader"
STAGE_VERSION = "1.0.0"


class ReaderBuildManifest(BaseModel):
    """Manifest recording what the reader build would produce."""

    doc_id: str
    run_id: str
    bundle_page_count: int = 0
    has_navigation: bool = False
    has_search: bool = False
    build_status: str = "pending"
    routes: list[str] = Field(default_factory=list)


@register_stage
class BuildReaderStage(BaseStage):
    """Build the static reader from the exported site bundle.

    V1: validates exported bundle exists and records build manifest.
    Future: shells out to pnpm build.
    """

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Build static reader from exported site bundle"

    def execute(self, ctx: StageContext) -> None:
        # Validate exported bundle exists
        bundle_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{ctx.doc_id}/bundle_manifest.json",
            SiteBundleManifest,
        )

        ctx.logger.info(
            "building_reader",
            page_count=bundle_manifest.page_count,
            mode="manifest-only",
        )

        # Build expected routes
        routes = [f"/docs/{ctx.doc_id}"]
        for page_num in range(1, bundle_manifest.page_count + 1):
            routes.append(f"/docs/{ctx.doc_id}/page/{page_num}")

        build_manifest = ReaderBuildManifest(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            bundle_page_count=bundle_manifest.page_count,
            has_navigation=bundle_manifest.has_navigation,
            has_search=bundle_manifest.has_search,
            build_status="manifest-only",
            routes=routes,
        )

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "build_manifest.json",
            build_manifest,
        )

        ctx.logger.info(
            "reader_build_complete",
            routes=len(routes),
            status="manifest-only",
        )
