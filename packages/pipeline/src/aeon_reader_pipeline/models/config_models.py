"""Document, pipeline, and profile configuration models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentTitles(BaseModel):
    """Localized document titles."""

    en: str
    ru: str


class DocumentProfiles(BaseModel):
    """Profile references for a document."""

    rules: str
    models: str
    symbols: str
    glossary: str
    patches: str | None = None


class DocumentBuild(BaseModel):
    """Build configuration for a document."""

    route_base: str
    include_in_catalog: bool = True


class DocumentNavigation(BaseModel):
    """Navigation overrides."""

    toc_overrides: list[dict[str, Any]] | None = None


class DocumentRender(BaseModel):
    """Render configuration."""

    default_theme: str = "light"
    figure_policy: str = "inline"
    page_label_offset: int | None = None


class DocumentConfig(BaseModel):
    """Human-authored document declaration."""

    doc_id: str
    slug: str
    source_pdf: str
    titles: DocumentTitles
    edition: str | None = None
    source_locale: str = "en"
    target_locale: str = "ru"
    profiles: DocumentProfiles
    build: DocumentBuild
    navigation: DocumentNavigation = Field(default_factory=DocumentNavigation)
    render: DocumentRender = Field(default_factory=DocumentRender)


class ModelProfile(BaseModel):
    """Model/provider/prompt configuration for LLM calls."""

    profile_id: str
    provider: str
    model: str
    fallback_provider: str | None = None
    fallback_model: str | None = None
    temperature: float = 0.1
    top_p: float = 0.9
    max_output_tokens: int = 4096
    prompt_bundle: str = "translate-v1"
    max_retries: int = Field(default=3, ge=1)
    retry_base_delay: float = Field(default=1.0, ge=0)
    retry_max_delay: float = Field(default=60.0, ge=0)
    input_price_per_mtok: float = Field(default=0.0, ge=0)
    output_price_per_mtok: float = Field(default=0.0, ge=0)
    cli_timeout: int = Field(default=180, ge=1)


class HeadingDetection(BaseModel):
    """Heading detection configuration."""

    min_font_size_ratio: float = 1.15
    max_heading_length: int = 200


class ParagraphRules(BaseModel):
    """Paragraph validation rules."""

    max_length_warning: int = 2000
    max_length_error: int = 5000


class ListDetection(BaseModel):
    """List detection configuration."""

    bullet_patterns: list[str] = Field(
        # bullet, en-dash, hyphen, right-pointing triangle
        default_factory=lambda: ["\u2022", "\u2013", "-", "\u25b6"]
    )


class SymbolDetection(BaseModel):
    """Symbol detection configuration."""

    min_confidence: float = 0.8


class QAGateConfig(BaseModel):
    """Quality gate thresholds for the evaluate_qa stage."""

    enabled: bool = True
    max_errors: int = 0
    max_warnings: int = 50


class ReleaseRules(BaseModel):
    """Release gate rules."""

    max_warnings: int = 50
    block_on_review: bool = False


class RuleProfile(BaseModel):
    """Thresholds and QA behavior configuration."""

    profile_id: str
    heading_detection: HeadingDetection = Field(default_factory=HeadingDetection)
    paragraph: ParagraphRules = Field(default_factory=ParagraphRules)
    list_detection: ListDetection = Field(default_factory=ListDetection)
    symbol_detection: SymbolDetection = Field(default_factory=SymbolDetection)
    release: ReleaseRules = Field(default_factory=ReleaseRules)
    qa_gate: QAGateConfig = Field(default_factory=QAGateConfig)


class SymbolDetectionConfig(BaseModel):
    """Detection signatures for a symbol."""

    image_hashes: list[str] = Field(default_factory=list)
    vector_signatures: list[str] = Field(default_factory=list)
    text_tokens: list[str] = Field(default_factory=list)


class SymbolEntry(BaseModel):
    """Single symbol definition."""

    symbol_id: str
    label_en: str
    label_ru: str
    aliases: list[str] = Field(default_factory=list)
    svg_path: str = ""
    alt_text: str = ""
    detection: SymbolDetectionConfig = Field(default_factory=SymbolDetectionConfig)
    render_component: str = ""
    search_tokens: list[str] = Field(default_factory=list)


class SymbolPack(BaseModel):
    """Canonical symbol registry."""

    pack_id: str
    version: str
    symbols: list[SymbolEntry] = Field(default_factory=list)


class GlossaryTermEntry(BaseModel):
    """Single glossary term."""

    term_id: str
    en_canonical: str
    en_aliases: list[str] = Field(default_factory=list)
    ru_preferred: str
    ru_variants: list[str] = Field(default_factory=list)
    lock_translation: bool = False
    link_policy: Literal["always", "first_only", "never"] = "first_only"
    doc_scope: list[str] = Field(default_factory=lambda: ["*"])
    definition_ru: str = ""
    definition_en: str | None = None
    notes: str | None = None


class GlossaryPack(BaseModel):
    """Canonical terminology pack."""

    pack_id: str
    version: str
    terms: list[GlossaryTermEntry] = Field(default_factory=list)


class PatchEntry(BaseModel):
    """Single deterministic override."""

    patch_id: str
    target_page: int | None = None
    target_block_id: str | None = None
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class PatchSet(BaseModel):
    """Deterministic page/block overrides."""

    doc_id: str
    version: str
    patches: list[PatchEntry] = Field(default_factory=list)


class CatalogConfig(BaseModel):
    """Root document catalog."""

    documents: list[str] = Field(default_factory=list)
    groups: dict[str, list[str]] = Field(default_factory=dict)
