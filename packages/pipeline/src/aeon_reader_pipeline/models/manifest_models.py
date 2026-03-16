"""Document manifest models describing source PDF structure."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageDimensions(BaseModel):
    """Physical page dimensions from PDF."""

    page_number: int
    width_pt: float
    height_pt: float
    rotation: int = 0


class OutlineEntry(BaseModel):
    """Single entry from the PDF outline/table-of-contents."""

    level: int
    title: str
    page_number: int | None = None


class SourceMetadata(BaseModel):
    """Metadata extracted from the PDF document info dictionary."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    creator: str | None = None
    producer: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None
    keywords: str | None = None


class DocumentManifest(BaseModel):
    """Immutable manifest describing a source PDF.

    Produced by the ingest_source stage (01_ingest/document_manifest.json).
    """

    doc_id: str
    source_pdf_path: str
    source_pdf_sha256: str
    file_size_bytes: int
    page_count: int
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    page_dimensions: list[PageDimensions] = Field(default_factory=list)
    outline: list[OutlineEntry] = Field(default_factory=list)
