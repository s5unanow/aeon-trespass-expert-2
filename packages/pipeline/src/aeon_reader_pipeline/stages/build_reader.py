"""Stage 12 — sync exported site bundle to the reader application directory.

This stage copies the exported bundle from the pipeline artifact store into the
reader's ``generated/`` directory and produces a catalog manifest.  The actual
Next.js static build is an explicit operator step (``make site-build``).

After this stage completes, ``apps/reader/generated/<doc_id>/`` contains
everything the reader needs to build a static site.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.site_bundle_models import SiteBundleManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "build_reader"
STAGE_VERSION = "2.0.0"


class ReaderBuildManifest(BaseModel):
    """Manifest recording the sync operation and expected routes."""

    doc_id: str
    run_id: str
    bundle_page_count: int = 0
    has_navigation: bool = False
    has_search: bool = False
    build_status: str = "pending"
    synced_files: int = 0
    reader_generated_dir: str = ""
    routes: list[str] = Field(default_factory=list)


def _reader_generated_dir(ctx: StageContext) -> Path:
    """Derive the reader generated directory from the project root.

    The project root is the parent of ``configs_root`` (which defaults to
    ``<project>/configs``).
    """
    project_root = ctx.configs_root.parent
    return project_root / "apps" / "reader" / "generated"


def _sync_bundle(ctx: StageContext, log: Any) -> tuple[Path, int]:
    """Copy the exported site bundle into the reader's generated directory.

    Returns (generated_doc_dir, file_count).
    """
    export_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "export_site_bundle")
    bundle_src = export_dir / "site_bundle" / ctx.doc_id

    if not bundle_src.exists():
        raise FileNotFoundError(f"Exported bundle not found: {bundle_src}")

    generated_root = _reader_generated_dir(ctx)
    generated_doc = generated_root / ctx.doc_id

    # Remove stale content and copy fresh bundle
    if generated_doc.exists():
        shutil.rmtree(generated_doc)
    shutil.copytree(bundle_src, generated_doc)

    # Count synced files
    file_count = sum(1 for _ in generated_doc.rglob("*") if _.is_file())

    log.info("bundle_synced", dest=str(generated_doc), files=file_count)
    return generated_doc, file_count


def _write_catalog(ctx: StageContext, bundle_manifest: SiteBundleManifest) -> None:
    """Write or update the catalog manifest in the generated root.

    Respects ``include_in_catalog`` from the document config: when False the
    document is removed from the catalog (or never added).
    """
    generated_root = _reader_generated_dir(ctx)
    catalog_path = generated_root / "catalog.json"

    # Load existing catalog or start fresh
    documents: list[dict[str, object]] = []
    if catalog_path.exists():
        existing = orjson.loads(catalog_path.read_bytes())
        documents = [d for d in existing.get("documents", []) if d.get("doc_id") != ctx.doc_id]

    if not ctx.document_config.build.include_in_catalog:
        # Write catalog without this doc
        catalog = {"documents": documents, "total_documents": len(documents)}
        tmp_path = catalog_path.with_suffix(".tmp")
        tmp_path.write_bytes(orjson.dumps(catalog, option=orjson.OPT_INDENT_2))
        tmp_path.rename(catalog_path)
        return

    documents.append(
        {
            "doc_id": bundle_manifest.doc_id,
            "slug": bundle_manifest.doc_id,
            "title_en": bundle_manifest.title_en,
            "title_ru": bundle_manifest.title_ru,
            "route_base": bundle_manifest.route_base,
            "page_count": bundle_manifest.page_count,
            "translation_coverage": bundle_manifest.translation_coverage,
        }
    )

    catalog = {"documents": documents, "total_documents": len(documents)}

    # Atomic write
    tmp_path = catalog_path.with_suffix(".tmp")
    tmp_path.write_bytes(orjson.dumps(catalog, option=orjson.OPT_INDENT_2))
    tmp_path.rename(catalog_path)


@register_stage
class BuildReaderStage(BaseStage):
    """Sync site bundle to the reader generated directory and write catalog.

    After this stage: ``apps/reader/generated/<doc_id>/`` is ready.
    Run ``make site-build`` to produce the static HTML output.
    """

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Sync site bundle to reader and build catalog"

    def execute(self, ctx: StageContext) -> None:
        # Read exported bundle manifest
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
        )

        # Sync bundle to reader
        generated_doc, file_count = _sync_bundle(ctx, ctx.logger)

        # Write/update catalog
        _write_catalog(ctx, bundle_manifest)

        # Build expected routes
        routes = [f"/docs/{ctx.doc_id}"]
        if bundle_manifest.filtered_pages is not None:
            for page_num in bundle_manifest.filtered_pages:
                routes.append(f"/docs/{ctx.doc_id}/page/{page_num}")
        else:
            for page_num in range(1, bundle_manifest.page_count + 1):
                routes.append(f"/docs/{ctx.doc_id}/page/{page_num}")

        build_manifest = ReaderBuildManifest(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            bundle_page_count=bundle_manifest.page_count,
            has_navigation=bundle_manifest.has_navigation,
            has_search=bundle_manifest.has_search,
            build_status="bundle-synced",
            synced_files=file_count,
            reader_generated_dir=str(generated_doc),
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
            synced_files=file_count,
            status="bundle-synced",
        )
