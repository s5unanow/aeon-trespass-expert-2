"""Shared enrichment output models — navigation, search, and document summary.

These are persisted stage outputs that cross stage boundaries. They live in
the model layer so that downstream stages, QA, contract generation, and tests
can import them without depending on stage modules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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
