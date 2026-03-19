"""Canonical intermediate representation models — PageRecord, Block, InlineNode."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

# ---------------------------------------------------------------------------
# Inline nodes — leaf-level content within a block
# ---------------------------------------------------------------------------


class TextRun(BaseModel):
    """Plain text run with optional formatting."""

    kind: Literal["text"] = "text"
    text: str
    ru_text: str | None = None
    bold: bool = False
    italic: bool = False
    monospace: bool = False
    font_name: str | None = None
    font_size: float | None = None


class SymbolRef(BaseModel):
    """Reference to a canonical symbol from a SymbolPack."""

    kind: Literal["symbol"] = "symbol"
    symbol_id: str
    alt_text: str = ""


class GlossaryRef(BaseModel):
    """Reference to a glossary term."""

    kind: Literal["glossary_ref"] = "glossary_ref"
    term_id: str
    surface_form: str
    ru_surface_form: str = ""


def _inline_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", "text"))
    return str(getattr(v, "kind", "text"))


InlineNode = Annotated[
    Annotated[TextRun, Tag("text")]
    | Annotated[SymbolRef, Tag("symbol")]
    | Annotated[GlossaryRef, Tag("glossary_ref")],
    Discriminator(_inline_discriminator),
]


# ---------------------------------------------------------------------------
# Block types — semantic page structure
# ---------------------------------------------------------------------------


class HeadingBlock(BaseModel):
    """Section heading."""

    kind: Literal["heading"] = "heading"
    block_id: str
    level: int = 1
    content: list[InlineNode] = Field(default_factory=list)
    anchor: str = ""
    source_block_index: int | None = None


class ParagraphBlock(BaseModel):
    """Normal text paragraph."""

    kind: Literal["paragraph"] = "paragraph"
    block_id: str
    content: list[InlineNode] = Field(default_factory=list)
    source_block_index: int | None = None


class ListItemBlock(BaseModel):
    """Single item in a list."""

    kind: Literal["list_item"] = "list_item"
    block_id: str
    bullet: str = ""
    content: list[InlineNode] = Field(default_factory=list)
    source_block_index: int | None = None


class ListBlock(BaseModel):
    """Ordered or unordered list container."""

    kind: Literal["list"] = "list"
    block_id: str
    list_type: Literal["unordered", "ordered"] = "unordered"
    items: list[ListItemBlock] = Field(default_factory=list)
    source_block_index: int | None = None


class FigureBlock(BaseModel):
    """Image or diagram reference."""

    kind: Literal["figure"] = "figure"
    block_id: str
    asset_ref: str = ""
    alt_text: str = ""
    caption_block_id: str | None = None
    source_block_index: int | None = None


class CaptionBlock(BaseModel):
    """Figure or table caption."""

    kind: Literal["caption"] = "caption"
    block_id: str
    content: list[InlineNode] = Field(default_factory=list)
    parent_block_id: str | None = None
    source_block_index: int | None = None


class TableCell(BaseModel):
    """A single cell in a table."""

    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1


class TableBlock(BaseModel):
    """Table with cell data."""

    kind: Literal["table"] = "table"
    block_id: str
    rows: int = 0
    cols: int = 0
    cells: list[TableCell] = Field(default_factory=list)
    source_block_index: int | None = None


class CalloutBlock(BaseModel):
    """Highlighted callout / sidebar / tip box."""

    kind: Literal["callout"] = "callout"
    block_id: str
    callout_type: str = "note"
    content: list[InlineNode] = Field(default_factory=list)
    source_block_index: int | None = None


class DividerBlock(BaseModel):
    """Horizontal rule or visual separator."""

    kind: Literal["divider"] = "divider"
    block_id: str
    source_block_index: int | None = None


def _block_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("kind", "paragraph"))
    return str(getattr(v, "kind", "paragraph"))


Block = Annotated[
    Annotated[HeadingBlock, Tag("heading")]
    | Annotated[ParagraphBlock, Tag("paragraph")]
    | Annotated[ListBlock, Tag("list")]
    | Annotated[ListItemBlock, Tag("list_item")]
    | Annotated[FigureBlock, Tag("figure")]
    | Annotated[CaptionBlock, Tag("caption")]
    | Annotated[TableBlock, Tag("table")]
    | Annotated[CalloutBlock, Tag("callout")]
    | Annotated[DividerBlock, Tag("divider")],
    Discriminator(_block_discriminator),
]


# ---------------------------------------------------------------------------
# Page-level record
# ---------------------------------------------------------------------------


class PageAnchor(BaseModel):
    """Named anchor on a page for cross-referencing."""

    anchor_id: str
    block_id: str
    label: str = ""


class PageRecord(BaseModel):
    """Canonical semantic representation of a single page.

    Produced by normalize_layout (03_normalize/pages/p0001.json).
    This is the core IR — deterministic structure, no LLM output.
    """

    page_number: int
    doc_id: str
    width_pt: float
    height_pt: float
    render_mode: Literal["semantic", "hybrid", "facsimile"] = "semantic"
    fallback_image_ref: str | None = None
    blocks: list[Block] = Field(default_factory=list)
    anchors: list[PageAnchor] = Field(default_factory=list)
    source_pdf_sha256: str = ""
    fingerprint: str = ""
