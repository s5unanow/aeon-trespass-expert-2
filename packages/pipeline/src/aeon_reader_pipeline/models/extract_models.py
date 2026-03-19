"""Extraction-phase models for raw text blocks and visual elements."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FontInfo(BaseModel):
    """Font metadata for a text span."""

    name: str
    size: float
    flags: int = 0
    color: int = 0
    is_bold: bool = False
    is_italic: bool = False
    is_monospace: bool = False


class BBox(BaseModel):
    """Bounding box in PDF points (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


class TextSpan(BaseModel):
    """A single contiguous run of text with uniform font."""

    text: str
    font: FontInfo
    bbox: BBox
    origin: tuple[float, float] | None = None


class TextLine(BaseModel):
    """A line of text composed of spans."""

    spans: list[TextSpan] = Field(default_factory=list)
    bbox: BBox
    writing_direction: str = "ltr"

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


class TextBlock(BaseModel):
    """A rectangular block of text composed of lines."""

    block_index: int
    lines: list[TextLine] = Field(default_factory=list)
    bbox: BBox
    block_type: str = "text"

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class RawImageInfo(BaseModel):
    """Metadata about a raw image found on a page."""

    image_index: int
    xref: int
    width: int
    height: int
    colorspace: str
    bpc: int
    bbox: BBox
    content_hash: str
    stored_as: str | None = None


class RawTableCell(BaseModel):
    """A single cell in a raw extracted table."""

    row: int
    col: int
    text: str
    row_span: int = 1
    col_span: int = 1


class RawTableInfo(BaseModel):
    """Raw table structure extracted from a PDF page."""

    table_index: int
    rows: int
    cols: int
    bbox: BBox
    cells: list[RawTableCell] = Field(default_factory=list)


class ExtractedPage(BaseModel):
    """Raw extraction output for a single PDF page.

    Produced by the extract_primitives stage (02_extract/pages/p0001.json).
    Contains raw text structure and image references — no semantic inference.
    """

    page_number: int
    width_pt: float
    height_pt: float
    rotation: int = 0
    text_blocks: list[TextBlock] = Field(default_factory=list)
    images: list[RawImageInfo] = Field(default_factory=list)
    tables: list[RawTableInfo] = Field(default_factory=list)
    fonts_used: list[str] = Field(default_factory=list)
    char_count: int = 0
    source_pdf_sha256: str = ""
    doc_id: str = ""
