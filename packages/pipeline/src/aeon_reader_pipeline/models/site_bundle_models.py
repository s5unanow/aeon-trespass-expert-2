"""Site bundle models for reader web application output.

These are the PUBLIC contracts consumed by the frontend reader.
They deliberately strip internal-only fields from pipeline IR models.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

# ---------------------------------------------------------------------------
# Public inline nodes — mirrors ir_models but without internal metadata
# ---------------------------------------------------------------------------


class BundleTextRun(BaseModel):
    """Public text run for the reader."""

    kind: Literal["text"] = "text"
    text: str
    ru_text: str | None = None
    bold: bool = False
    italic: bool = False
    monospace: bool = False


class BundleSymbolRef(BaseModel):
    """Public symbol reference for the reader."""

    kind: Literal["symbol"] = "symbol"
    symbol_id: str
    alt_text: str = ""
    label: str = ""
    svg_data: str = ""


class BundleGlossaryRef(BaseModel):
    """Public glossary reference for the reader."""

    kind: Literal["glossary_ref"] = "glossary_ref"
    term_id: str
    surface_form: str
    ru_surface_form: str = ""


def _bundle_inline_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", "text"))
    return str(getattr(v, "kind", "text"))


BundleInlineNode = Annotated[
    Annotated[BundleTextRun, Tag("text")]
    | Annotated[BundleSymbolRef, Tag("symbol")]
    | Annotated[BundleGlossaryRef, Tag("glossary_ref")],
    Discriminator(_bundle_inline_discriminator),
]


# ---------------------------------------------------------------------------
# Public block types — mirrors ir_models without source_block_index
# ---------------------------------------------------------------------------


class BundleHeadingBlock(BaseModel):
    """Public heading block."""

    kind: Literal["heading"] = "heading"
    block_id: str
    level: int = 1
    content: list[BundleInlineNode] = Field(default_factory=list)
    anchor: str = ""


class BundleParagraphBlock(BaseModel):
    """Public paragraph block."""

    kind: Literal["paragraph"] = "paragraph"
    block_id: str
    content: list[BundleInlineNode] = Field(default_factory=list)


class BundleListItemBlock(BaseModel):
    """Public list item block."""

    kind: Literal["list_item"] = "list_item"
    block_id: str
    bullet: str = ""
    content: list[BundleInlineNode] = Field(default_factory=list)


class BundleListBlock(BaseModel):
    """Public list container block."""

    kind: Literal["list"] = "list"
    block_id: str
    list_type: Literal["unordered", "ordered"] = "unordered"
    items: list[BundleListItemBlock] = Field(default_factory=list)


class BundleFigureBlock(BaseModel):
    """Public figure block."""

    kind: Literal["figure"] = "figure"
    block_id: str
    asset_ref: str = ""
    alt_text: str = ""
    caption_block_id: str | None = None


class BundleCaptionBlock(BaseModel):
    """Public caption block."""

    kind: Literal["caption"] = "caption"
    block_id: str
    content: list[BundleInlineNode] = Field(default_factory=list)
    parent_block_id: str | None = None


class BundleTableCell(BaseModel):
    """Public table cell."""

    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1


class BundleTableBlock(BaseModel):
    """Public table block."""

    kind: Literal["table"] = "table"
    block_id: str
    rows: int = 0
    cols: int = 0
    cells: list[BundleTableCell] = Field(default_factory=list)


class BundleCalloutBlock(BaseModel):
    """Public callout block."""

    kind: Literal["callout"] = "callout"
    block_id: str
    callout_type: str = "note"
    content: list[BundleInlineNode] = Field(default_factory=list)


class BundleDividerBlock(BaseModel):
    """Public divider block."""

    kind: Literal["divider"] = "divider"
    block_id: str


def _bundle_block_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", "paragraph"))
    return str(getattr(v, "kind", "paragraph"))


BundleBlock = Annotated[
    Annotated[BundleHeadingBlock, Tag("heading")]
    | Annotated[BundleParagraphBlock, Tag("paragraph")]
    | Annotated[BundleListBlock, Tag("list")]
    | Annotated[BundleListItemBlock, Tag("list_item")]
    | Annotated[BundleFigureBlock, Tag("figure")]
    | Annotated[BundleCaptionBlock, Tag("caption")]
    | Annotated[BundleTableBlock, Tag("table")]
    | Annotated[BundleCalloutBlock, Tag("callout")]
    | Annotated[BundleDividerBlock, Tag("divider")],
    Discriminator(_bundle_block_discriminator),
]


# ---------------------------------------------------------------------------
# Public page-level record
# ---------------------------------------------------------------------------


class BundlePageAnchor(BaseModel):
    """Public named anchor on a page."""

    anchor_id: str
    block_id: str
    label: str = ""


class BundlePage(BaseModel):
    """Public reader-facing page payload.

    This is the transport boundary between pipeline and frontend.
    It mirrors PageRecord but strips internal-only fields:
    - source_pdf_sha256, fingerprint (provenance)
    - source_block_index on all blocks (extraction tracking)
    - font_name, font_size on text runs (extraction metadata)
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float
    render_mode: Literal["semantic", "hybrid", "facsimile"] = "semantic"
    blocks: list[BundleBlock] = Field(default_factory=list)
    anchors: list[BundlePageAnchor] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bundle-level manifests
# ---------------------------------------------------------------------------


class BundleAssetEntry(BaseModel):
    """Single asset in the bundle."""

    asset_ref: str
    path: str
    content_type: str = ""
    size_bytes: int = 0


class SiteBundleManifest(BaseModel):
    """Root manifest for an exported site bundle.

    Lives at 11_export/site_bundle/<doc_id>/bundle_manifest.json
    """

    doc_id: str
    run_id: str
    page_count: int
    title_en: str
    title_ru: str = ""
    route_base: str = ""
    source_locale: str = "en"
    target_locale: str = "ru"
    translation_coverage: float = 0.0
    has_navigation: bool = False
    has_search: bool = False
    has_glossary: bool = False
    assets: list[BundleAssetEntry] = Field(default_factory=list)
    qa_accepted: bool = True
    stage_version: str = "1.0.0"


class BundleGlossaryEntry(BaseModel):
    """Public glossary entry for the reader drawer."""

    term_id: str
    en_canonical: str
    ru_preferred: str
    definition_ru: str = ""
    definition_en: str | None = None


class BundleGlossary(BaseModel):
    """Glossary data exported for the reader."""

    doc_id: str
    entries: list[BundleGlossaryEntry] = Field(default_factory=list)
    total_entries: int = 0


class CatalogEntry(BaseModel):
    """Single document entry in the reader catalog."""

    doc_id: str
    slug: str
    title_en: str
    title_ru: str = ""
    route_base: str = ""
    page_count: int = 0
    translation_coverage: float = 0.0


class CatalogManifest(BaseModel):
    """Multi-document catalog manifest for the reader root."""

    documents: list[CatalogEntry] = Field(default_factory=list)
    total_documents: int = 0


class BuildArtifact(BaseModel):
    """Inventory entry for an exported artifact."""

    path: str
    artifact_type: str
    size_bytes: int = 0
    checksum: str = ""


class BuildArtifacts(BaseModel):
    """Export inventory manifest.

    Lives at 11_export/build_artifacts.json
    """

    doc_id: str
    run_id: str
    artifacts: list[BuildArtifact] = Field(default_factory=list)
    total_artifacts: int = 0
