"""Translation unit and localization bundle models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Translation planning — input to LLM
# ---------------------------------------------------------------------------


class GlossaryHint(BaseModel):
    """Glossary term hint included with a translation unit."""

    en: str
    ru: str
    locked: bool = False


class TextNode(BaseModel):
    """Single translatable text node within a unit."""

    inline_id: str
    source_text: str


class TranslationUnit(BaseModel):
    """Bounded group of text nodes sent to the LLM for translation.

    Units are the atomic work item for translation — each contains a small
    set of semantically related text nodes from the same page/section.
    """

    unit_id: str
    doc_id: str
    page_number: int
    block_ids: list[str] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    style_hint: str = "paragraph"
    glossary_subset: list[GlossaryHint] = Field(default_factory=list)
    text_nodes: list[TextNode] = Field(default_factory=list)
    context_before: str = ""
    context_after: str = ""
    source_fingerprint: str = ""


class TranslationPlan(BaseModel):
    """Collection of all translation units for a document."""

    doc_id: str
    source_locale: str = "en"
    target_locale: str = "ru"
    total_units: int = 0
    total_text_nodes: int = 0
    units: list[TranslationUnit] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Translation result — output from LLM
# ---------------------------------------------------------------------------


class TranslatedNode(BaseModel):
    """Single translated text node returned by the LLM."""

    inline_id: str
    ru_text: str


class TranslationResult(BaseModel):
    """Validated result for a single translation unit."""

    unit_id: str
    translations: list[TranslatedNode] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    prompt_bundle: str = ""
    source_fingerprint: str = ""
    result_fingerprint: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attempt: int = 1
    cached: bool = False


class TranslationFailure(BaseModel):
    """Record of a failed translation attempt."""

    unit_id: str
    error_type: str
    error_message: str
    provider: str = ""
    model: str = ""
    attempt: int = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_response: str = ""


class TranslationCallMetadata(BaseModel):
    """Metadata about an LLM call for auditability."""

    unit_id: str
    provider: str
    model: str
    prompt_bundle: str
    temperature: float = 0.1
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cache_hit: bool = False


# ---------------------------------------------------------------------------
# Stage summary artifacts
# ---------------------------------------------------------------------------


class TranslationPlanSummary(BaseModel):
    """Summary written by plan_translation stage."""

    doc_id: str
    page_count: int
    total_units: int
    total_text_nodes: int
    skipped_pages: list[int] = Field(default_factory=list)


class TranslationStageSummary(BaseModel):
    """Summary written by translate_units stage."""

    doc_id: str
    total_units: int
    completed: int = 0
    failed: int = 0
    cached: int = 0
    status: Literal["completed", "partial", "failed"] = "completed"
    errors: list[dict[str, Any]] = Field(default_factory=list)
