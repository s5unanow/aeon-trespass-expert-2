"""Stage 1 — ingest source PDF and produce DocumentManifest."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from aeon_reader_pipeline.config.hashing import hash_file
from aeon_reader_pipeline.models.manifest_models import (
    DocumentManifest,
    OutlineEntry,
    PageDimensions,
    SourceMetadata,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "ingest_source"
STAGE_VERSION = "1.0.0"


def _resolve_source_path(ctx: StageContext) -> Path:
    """Resolve the source PDF path relative to configs root."""
    raw = ctx.document_config.source_pdf
    path = Path(raw)
    if path.is_absolute():
        return path
    # Resolve relative to the repo root (parent of configs/)
    return ctx.configs_root.parent / path


def _extract_metadata(doc: pymupdf.Document) -> SourceMetadata:
    """Extract metadata from the PDF info dictionary."""
    meta = doc.metadata or {}
    return SourceMetadata(
        title=meta.get("title") or None,
        author=meta.get("author") or None,
        subject=meta.get("subject") or None,
        creator=meta.get("creator") or None,
        producer=meta.get("producer") or None,
        creation_date=meta.get("creationDate") or None,
        modification_date=meta.get("modDate") or None,
        keywords=meta.get("keywords") or None,
    )


def _extract_page_dimensions(doc: pymupdf.Document) -> list[PageDimensions]:
    """Extract dimensions for every page."""
    dims: list[PageDimensions] = []
    for i in range(len(doc)):
        page = doc[i]
        rect = page.rect
        dims.append(
            PageDimensions(
                page_number=i + 1,
                width_pt=round(rect.width, 2),
                height_pt=round(rect.height, 2),
                rotation=page.rotation,
            )
        )
    return dims


def _extract_outline(doc: pymupdf.Document) -> list[OutlineEntry]:
    """Extract the document outline (table of contents)."""
    toc = doc.get_toc(simple=True)
    entries: list[OutlineEntry] = []
    for level, title, page_num in toc:
        entries.append(
            OutlineEntry(
                level=level,
                title=title,
                page_number=page_num if page_num > 0 else None,
            )
        )
    return entries


@register_stage
class IngestSourceStage(BaseStage):
    """Ingest a source PDF and produce an immutable DocumentManifest."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Hash PDF, capture metadata, page count, dimensions, and outline"

    def execute(self, ctx: StageContext) -> None:
        source_path = _resolve_source_path(ctx)
        if not source_path.exists():
            raise FileNotFoundError(f"Source PDF not found: {source_path}")

        ctx.logger.info("ingesting_source", source_path=str(source_path))

        pdf_hash = hash_file(str(source_path))
        file_size = source_path.stat().st_size

        doc = pymupdf.open(str(source_path))
        try:
            manifest = DocumentManifest(
                doc_id=ctx.doc_id,
                source_pdf_path=str(source_path),
                source_pdf_sha256=pdf_hash,
                file_size_bytes=file_size,
                page_count=len(doc),
                metadata=_extract_metadata(doc),
                page_dimensions=_extract_page_dimensions(doc),
                outline=_extract_outline(doc),
            )
        finally:
            doc.close()

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "document_manifest.json",
            manifest,
        )

        ctx.logger.info(
            "ingest_complete",
            page_count=manifest.page_count,
            sha256=manifest.source_pdf_sha256[:16],
        )
