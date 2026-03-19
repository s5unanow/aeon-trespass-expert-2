"""Stage 13 — build search index from finalized content.

This stage wraps Pagefind indexing. In v1 it records a search index manifest
and validates that search documents exist. The actual Pagefind build is deferred
to EP-010 when the reader and search integration are implemented.
"""

from __future__ import annotations

from pydantic import BaseModel

from aeon_reader_pipeline.models.enrich_models import SearchIndex
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "index_search"
STAGE_VERSION = "1.0.0"


class SearchIndexManifest(BaseModel):
    """Manifest recording what the search index would produce."""

    doc_id: str
    run_id: str
    total_documents: int = 0
    index_status: str = "pending"


@register_stage
class IndexSearchStage(BaseStage):
    """Build search index from exported search documents.

    V1: validates search documents exist and records manifest.
    Future: shells out to Pagefind.
    """

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Build search index from exported content"

    def execute(self, ctx: StageContext) -> None:
        # Try to read search documents from the exported bundle
        total_docs = 0
        try:
            search = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "export_site_bundle",
                f"site_bundle/{ctx.doc_id}/search_documents.json",
                SearchIndex,
            )
            total_docs = search.total_documents
        except FileNotFoundError:
            ctx.logger.warning("search_documents_not_found_for_indexing")

        ctx.logger.info(
            "indexing_search",
            total_documents=total_docs,
            mode="manifest-only",
        )

        index_manifest = SearchIndexManifest(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            total_documents=total_docs,
            index_status="manifest-only",
        )

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "search_index_manifest.json",
            index_manifest,
        )

        ctx.logger.info(
            "search_index_complete",
            documents=total_docs,
            status="manifest-only",
        )
