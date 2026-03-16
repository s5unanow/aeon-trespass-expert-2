"""Stage 8 — enrich content with glossary links, cross-references, and metadata."""

from __future__ import annotations

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.ir_models import (
    HeadingBlock,
    PageRecord,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.glossary_linker import link_glossary_terms

STAGE_NAME = "enrich_content"
STAGE_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Navigation models
# ---------------------------------------------------------------------------


class NavEntry(BaseModel):
    """Single entry in the navigation tree."""

    anchor_id: str
    block_id: str
    label_en: str
    label_ru: str = ""
    level: int = 1
    page_number: int
    children: list[NavEntry] = Field(default_factory=list)


class NavigationTree(BaseModel):
    """Full document navigation derived from heading structure."""

    doc_id: str
    entries: list[NavEntry] = Field(default_factory=list)
    total_entries: int = 0


# ---------------------------------------------------------------------------
# Search document models
# ---------------------------------------------------------------------------


class SearchDocument(BaseModel):
    """Single searchable document unit for Pagefind indexing."""

    doc_id: str
    page_number: int
    block_id: str
    content_en: str
    content_ru: str = ""
    section_path: list[str] = Field(default_factory=list)
    heading: str = ""
    kind: str = "paragraph"


class SearchIndex(BaseModel):
    """Collection of search documents for a document."""

    doc_id: str
    documents: list[SearchDocument] = Field(default_factory=list)
    total_documents: int = 0


# ---------------------------------------------------------------------------
# Document summary
# ---------------------------------------------------------------------------


class DocumentSummary(BaseModel):
    """Metadata summary for the document catalog."""

    doc_id: str
    title_en: str
    title_ru: str
    page_count: int
    block_count: int = 0
    heading_count: int = 0
    translation_coverage: float = 0.0
    source_locale: str = "en"
    target_locale: str = "ru"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(block: HeadingBlock, locale: str = "en") -> str:
    """Extract text content from a heading block."""
    parts: list[str] = []
    for node in block.content:
        if isinstance(node, TextRun):
            if locale == "ru" and node.ru_text:
                parts.append(node.ru_text)
            else:
                parts.append(node.text)
    return " ".join(parts)


def _build_navigation(
    pages: list[PageRecord],
    doc_id: str,
) -> NavigationTree:
    """Build navigation tree from heading blocks across all pages."""
    entries: list[NavEntry] = []

    for record in pages:
        for block in record.blocks:
            if isinstance(block, HeadingBlock) and block.anchor:
                label_en = _extract_text(block, "en")
                label_ru = _extract_text(block, "ru")
                entry = NavEntry(
                    anchor_id=block.anchor,
                    block_id=block.block_id,
                    label_en=label_en,
                    label_ru=label_ru or label_en,
                    level=block.level,
                    page_number=record.page_number,
                )
                entries.append(entry)

    # Nest entries: level 2+ become children of preceding level 1
    nested = _nest_entries(entries)

    return NavigationTree(
        doc_id=doc_id,
        entries=nested,
        total_entries=len(entries),
    )


def _nest_entries(flat: list[NavEntry]) -> list[NavEntry]:
    """Convert flat heading list into nested tree (level 1 with children)."""
    result: list[NavEntry] = []
    current_parent: NavEntry | None = None

    for entry in flat:
        if entry.level == 1:
            current_parent = entry
            result.append(entry)
        elif current_parent is not None:
            current_parent.children.append(entry)
        else:
            # Orphan sub-heading — promote to top level
            result.append(entry)

    return result


def _build_search_documents(
    pages: list[PageRecord],
    doc_id: str,
) -> list[SearchDocument]:
    """Generate search documents from page content."""
    docs: list[SearchDocument] = []
    current_heading = ""

    for record in pages:
        section_path: list[str] = []
        for block in record.blocks:
            if isinstance(block, HeadingBlock):
                heading_text = _extract_text(block, "en")
                current_heading = heading_text
                if block.level == 1:
                    section_path = [heading_text]
                else:
                    section_path.append(heading_text)

            if not hasattr(block, "content"):
                continue

            en_parts: list[str] = []
            ru_parts: list[str] = []
            for node in block.content:
                if isinstance(node, TextRun):
                    en_parts.append(node.text)
                    if node.ru_text:
                        ru_parts.append(node.ru_text)

            content_en = " ".join(en_parts).strip()
            if not content_en:
                continue

            docs.append(
                SearchDocument(
                    doc_id=doc_id,
                    page_number=record.page_number,
                    block_id=block.block_id,
                    content_en=content_en,
                    content_ru=" ".join(ru_parts).strip(),
                    section_path=list(section_path),
                    heading=current_heading,
                    kind=block.kind,
                )
            )

    return docs


def _compute_coverage(pages: list[PageRecord]) -> float:
    """Compute translation coverage as ratio of translated text nodes."""
    total = 0
    translated = 0
    for record in pages:
        for block in record.blocks:
            if not hasattr(block, "content"):
                continue
            for node in block.content:
                if isinstance(node, TextRun) and node.text.strip():
                    total += 1
                    if node.ru_text:
                        translated += 1
    return translated / total if total > 0 else 0.0


@register_stage
class EnrichContentStage(BaseStage):
    """Enrich localized pages with glossary links, navigation, and search docs."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Add glossary annotations, build navigation tree and search index"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        ctx.logger.info("enriching_content", page_count=manifest.page_count)

        # Load all localized pages
        pages: list[PageRecord] = []
        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "merge_localization",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )
            pages.append(record)

        # Apply glossary linking
        enriched_pages: list[PageRecord] = []
        for record in pages:
            linked_blocks = link_glossary_terms(
                record.blocks,
                ctx.glossary_pack,
                ctx.doc_id,
            )
            enriched = record.model_copy(update={"blocks": linked_blocks})
            enriched_pages.append(enriched)

        # Write enriched pages
        for record in enriched_pages:
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{record.page_number:04d}.json",
                record,
            )

        # Build navigation tree
        nav = _build_navigation(enriched_pages, ctx.doc_id)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "navigation.json",
            nav,
        )

        # Build search documents
        search_docs = _build_search_documents(enriched_pages, ctx.doc_id)
        search_index = SearchIndex(
            doc_id=ctx.doc_id,
            documents=search_docs,
            total_documents=len(search_docs),
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "search_documents.json",
            search_index,
        )

        # Build document summary
        total_blocks = sum(len(r.blocks) for r in enriched_pages)
        heading_count = sum(
            1 for r in enriched_pages for b in r.blocks if isinstance(b, HeadingBlock)
        )
        coverage = _compute_coverage(enriched_pages)

        summary = DocumentSummary(
            doc_id=ctx.doc_id,
            title_en=ctx.document_config.titles.en,
            title_ru=ctx.document_config.titles.ru,
            page_count=manifest.page_count,
            block_count=total_blocks,
            heading_count=heading_count,
            translation_coverage=coverage,
            source_locale=ctx.document_config.source_locale,
            target_locale=ctx.document_config.target_locale,
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "doc_summary.json",
            summary,
        )

        ctx.logger.info(
            "enrichment_complete",
            pages=manifest.page_count,
            nav_entries=nav.total_entries,
            search_docs=len(search_docs),
            coverage=f"{coverage:.1%}",
        )
