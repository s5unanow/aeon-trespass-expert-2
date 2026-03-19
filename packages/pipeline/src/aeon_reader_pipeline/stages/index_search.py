"""Stage 13 — validate and record search index readiness.

This stage reads the exported search documents from stage 11, validates that
searchable content exists for the document, and records an index manifest with
actual document counts and coverage statistics.

Pagefind indexing runs as a post-build operator step (``make build-search``)
after the static site has been built.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.enrich_models import SearchIndex
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "index_search"
STAGE_VERSION = "2.0.0"


class SearchIndexManifest(BaseModel):
    """Manifest recording search index readiness."""

    doc_id: str
    run_id: str
    total_documents: int = 0
    pages_with_content: int = 0
    index_status: str = "pending"
    kinds: dict[str, int] = Field(default_factory=dict)


@register_stage
class IndexSearchStage(BaseStage):
    """Validate search data completeness and record index manifest.

    After this stage the search documents are verified.
    Run ``make build-search`` after ``make site-build`` for Pagefind indexing.
    """

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Validate search data and record index manifest"

    def execute(self, ctx: StageContext) -> None:
        total_docs = 0
        pages_with_content: set[int] = set()
        kinds: dict[str, int] = {}

        try:
            search = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "export_site_bundle",
                f"site_bundle/{ctx.doc_id}/search_documents.json",
                SearchIndex,
            )
            total_docs = search.total_documents
            for doc in search.documents:
                pages_with_content.add(doc.page_number)
                kind = doc.kind
                kinds[kind] = kinds.get(kind, 0) + 1
        except FileNotFoundError:
            ctx.logger.warning("search_documents_not_found_for_indexing")

        ctx.logger.info(
            "indexing_search",
            total_documents=total_docs,
            pages_with_content=len(pages_with_content),
        )

        index_manifest = SearchIndexManifest(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            total_documents=total_docs,
            pages_with_content=len(pages_with_content),
            index_status="search-data-validated" if total_docs > 0 else "no-search-data",
            kinds=kinds,
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
            status=index_manifest.index_status,
        )
