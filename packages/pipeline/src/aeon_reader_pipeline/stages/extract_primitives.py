"""Stage 2 — extract raw text blocks, images, and visual primitives from pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

from aeon_reader_pipeline.config.hashing import hash_bytes
from aeon_reader_pipeline.models.evidence_builder import build_primitive_evidence
from aeon_reader_pipeline.models.extract_models import (
    BBox,
    ExtractedPage,
    FontInfo,
    RawImageInfo,
    RawTableCell,
    RawTableInfo,
    TextBlock,
    TextLine,
    TextSpan,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "extract_primitives"
STAGE_VERSION = "1.0.0"


def _font_flags(flags: int) -> tuple[bool, bool, bool]:
    """Decode PyMuPDF font flags to bold/italic/monospace."""
    is_bold = bool(flags & (1 << 4))
    is_italic = bool(flags & (1 << 1))
    is_monospace = bool(flags & (1 << 0))
    return is_bold, is_italic, is_monospace


def _extract_text_blocks(page: pymupdf.Page) -> tuple[list[TextBlock], set[str], int]:
    """Extract text blocks with full line/span structure from a page.

    Returns (blocks, fonts_used, char_count).
    """
    blocks: list[TextBlock] = []
    fonts_used: set[str] = set()
    char_count = 0

    raw_dict = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

    for block_idx, block in enumerate(raw_dict.get("blocks", [])):
        if block.get("type") != 0:  # 0 = text block
            continue

        block_bbox = BBox(
            x0=block["bbox"][0],
            y0=block["bbox"][1],
            x1=block["bbox"][2],
            y1=block["bbox"][3],
        )

        text_lines: list[TextLine] = []
        for line in block.get("lines", []):
            line_bbox = BBox(
                x0=line["bbox"][0],
                y0=line["bbox"][1],
                x1=line["bbox"][2],
                y1=line["bbox"][3],
            )
            wdir = line.get("dir", (1.0, 0.0))
            writing_direction = "ltr" if wdir[0] >= 0 else "rtl"

            spans: list[TextSpan] = []
            for span in line.get("spans", []):
                text = span.get("text", "")
                if not text:
                    continue
                char_count += len(text)

                font_name = span.get("font", "unknown")
                fonts_used.add(font_name)
                flags = span.get("flags", 0)
                is_bold, is_italic, is_monospace = _font_flags(flags)

                font_info = FontInfo(
                    name=font_name,
                    size=round(span.get("size", 0.0), 2),
                    flags=flags,
                    color=span.get("color", 0),
                    is_bold=is_bold,
                    is_italic=is_italic,
                    is_monospace=is_monospace,
                )
                span_bbox = BBox(
                    x0=span["bbox"][0],
                    y0=span["bbox"][1],
                    x1=span["bbox"][2],
                    y1=span["bbox"][3],
                )
                origin = tuple(span["origin"]) if "origin" in span else None

                spans.append(
                    TextSpan(
                        text=text,
                        font=font_info,
                        bbox=span_bbox,
                        origin=origin,
                    )
                )

            if spans:
                text_lines.append(
                    TextLine(
                        spans=spans,
                        bbox=line_bbox,
                        writing_direction=writing_direction,
                    )
                )

        if text_lines:
            blocks.append(
                TextBlock(
                    block_index=block_idx,
                    lines=text_lines,
                    bbox=block_bbox,
                    block_type="text",
                )
            )

    return blocks, fonts_used, char_count


def _extract_images(
    page: pymupdf.Page,
    doc: pymupdf.Document,
    stage_dir: Path,
    page_number: int = 0,
    *,
    ctx: StageContext,
) -> tuple[list[RawImageInfo], int]:
    """Extract raw images from a page, save to assets directory.

    Returns (images, failure_count).
    """
    images: list[RawImageInfo] = []
    image_list = page.get_images(full=True)
    failures = 0

    if not image_list:
        return images, failures

    assets_dir = stage_dir / "assets" / "raw"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for img_idx, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
        except Exception as exc:
            failures += 1
            ctx.logger.warning(
                "image_extraction_failed",
                page=page_number,
                image_index=img_idx,
                xref=xref,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            ctx.errors.record(
                error_type=type(exc).__name__,
                message=str(exc),
                page=page_number,
                image_index=img_idx,
                xref=xref,
            )
            continue

        if not base_image or not base_image.get("image"):
            continue

        image_data = base_image["image"]
        content_hash = hash_bytes(image_data)
        ext = base_image.get("ext", "png")
        filename = f"{content_hash[:16]}.{ext}"

        asset_path = assets_dir / filename
        if not asset_path.exists():
            asset_path.write_bytes(image_data)

        # Get image bbox on the page
        img_rects = page.get_image_rects(xref)
        if img_rects:
            rect = img_rects[0]
            bbox = BBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)
        else:
            bbox = BBox(
                x0=0,
                y0=0,
                x1=float(base_image.get("width", 0)),
                y1=float(base_image.get("height", 0)),
            )

        images.append(
            RawImageInfo(
                image_index=img_idx,
                xref=xref,
                width=base_image.get("width", 0),
                height=base_image.get("height", 0),
                colorspace=base_image.get("colorspace_n", 0).__class__.__name__
                if not isinstance(base_image.get("cs-name", ""), str)
                else base_image.get("cs-name", "unknown"),
                bpc=base_image.get("bpc", 8),
                bbox=bbox,
                content_hash=content_hash,
                stored_as=filename,
            )
        )

    return images, failures


_TABLE_STRATEGIES: list[str] = ["lines_strict", "lines", "text"]
"""Ordered table-detection strategies — strictest first, broadest last."""


def _try_find_tables(
    page: pymupdf.Page,
    strategy: str,
) -> list[Any] | None:
    """Attempt ``page.find_tables`` with a given strategy.

    Returns the list of detected tables on success, or *None* if the
    strategy is not supported by the installed PyMuPDF version.
    """
    try:
        finder = page.find_tables(strategy=strategy)  # type: ignore[attr-defined]
        return list(finder.tables)
    except TypeError:
        # PyMuPDF version does not support the strategy keyword
        return None


def _extract_tables(
    page: pymupdf.Page,
    *,
    ctx: StageContext,
    page_number: int,
) -> list[RawTableInfo]:
    """Extract table structures from a page using PyMuPDF's table finder.

    Tries strategies in deterministic order (``lines_strict`` → ``lines`` →
    ``text``).  The first strategy that yields any tables wins; its name is
    recorded on every :class:`RawTableInfo` for downstream provenance.
    """
    # Try each strategy in order; first one to produce results wins.
    raw_tables: list[Any] = []
    chosen_strategy = "default"

    for strategy in _TABLE_STRATEGIES:
        try:
            result = _try_find_tables(page, strategy)
        except Exception as exc:
            ctx.logger.warning(
                "table_detection_failed",
                page=page_number,
                strategy=strategy,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        if result is None:
            # Strategy keyword not supported — fall through to default
            break
        if result:
            raw_tables = result
            chosen_strategy = strategy
            break
    else:
        # All strategies either returned empty or errored — already handled.
        pass

    # Fallback: plain find_tables() without strategy kwarg
    if not raw_tables:
        try:
            finder: Any = page.find_tables()  # type: ignore[attr-defined]
            raw_tables = list(finder.tables)
            chosen_strategy = "default"
        except Exception as exc:
            ctx.logger.warning(
                "table_detection_failed",
                page=page_number,
                strategy="default",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

    tables: list[RawTableInfo] = []
    for tbl_idx, table in enumerate(raw_tables):
        try:
            bbox = BBox(x0=table.bbox[0], y0=table.bbox[1], x1=table.bbox[2], y1=table.bbox[3])
            extracted = table.extract()
            row_count = len(extracted)
            col_count = table.col_count
            cells: list[RawTableCell] = []
            for r_idx, row in enumerate(extracted):
                for c_idx, cell_text in enumerate(row):
                    cells.append(
                        RawTableCell(
                            row=r_idx,
                            col=c_idx,
                            text=cell_text or "",
                        )
                    )
            tables.append(
                RawTableInfo(
                    table_index=tbl_idx,
                    rows=row_count,
                    cols=col_count,
                    bbox=bbox,
                    cells=cells,
                    extraction_strategy=chosen_strategy,
                )
            )
        except Exception as exc:
            ctx.logger.warning(
                "table_extraction_failed",
                page=page_number,
                table_index=tbl_idx,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            ctx.errors.record(
                error_type=type(exc).__name__,
                message=str(exc),
                page=page_number,
                table_index=tbl_idx,
            )
    return tables


def _page_filename(page_number: int) -> str:
    """Generate the canonical per-page filename."""
    return f"pages/p{page_number:04d}.json"


def _evidence_filename(page_number: int) -> str:
    """Generate the canonical per-page evidence filename."""
    return f"evidence/p{page_number:04d}_primitive.json"


@register_stage
class ExtractPrimitivesStage(BaseStage):
    """Extract raw text blocks, images, and visual primitives from each page."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Extract per-page text structure and raw assets from PDF"

    def execute(self, ctx: StageContext) -> None:
        # Load the document manifest from the previous stage
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        source_path = Path(manifest.source_pdf_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source PDF not found: {source_path}")

        ctx.logger.info(
            "extracting_primitives",
            page_count=manifest.page_count,
            source=str(source_path),
        )

        stage_dir = ctx.artifact_store.ensure_stage_dir(ctx.run_id, ctx.doc_id, STAGE_NAME)

        doc = pymupdf.open(str(source_path))
        total_image_failures = 0
        page_filter_set = (
            frozenset(ctx.pipeline_config.page_filter)
            if ctx.pipeline_config.page_filter is not None
            else None
        )
        try:
            for page_idx in range(len(doc)):
                page_number = page_idx + 1
                if page_filter_set is not None and page_number not in page_filter_set:
                    continue
                page = doc[page_idx]

                text_blocks, fonts_used, char_count = _extract_text_blocks(page)
                images, img_failures = _extract_images(
                    page,
                    doc,
                    stage_dir,
                    page_number=page_number,
                    ctx=ctx,
                )
                total_image_failures += img_failures
                raw_tables = _extract_tables(page, ctx=ctx, page_number=page_number)

                rect = page.rect
                extracted = ExtractedPage(
                    page_number=page_number,
                    width_pt=round(rect.width, 2),
                    height_pt=round(rect.height, 2),
                    rotation=page.rotation,
                    text_blocks=text_blocks,
                    images=images,
                    tables=raw_tables,
                    fonts_used=sorted(fonts_used),
                    char_count=char_count,
                    source_pdf_sha256=manifest.source_pdf_sha256,
                    doc_id=ctx.doc_id,
                )

                ctx.artifact_store.write_artifact(
                    ctx.run_id,
                    ctx.doc_id,
                    STAGE_NAME,
                    _page_filename(page_number),
                    extracted,
                )

                # Emit provenance-tagged evidence with normalized coordinates
                try:
                    evidence = build_primitive_evidence(extracted)
                    ctx.artifact_store.write_artifact(
                        ctx.run_id,
                        ctx.doc_id,
                        STAGE_NAME,
                        _evidence_filename(page_number),
                        evidence,
                    )
                except Exception as exc:
                    ctx.logger.warning(
                        "evidence_emission_failed",
                        page=page_number,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    ctx.errors.record(
                        error_type=type(exc).__name__,
                        message=f"Evidence emission failed: {exc}",
                        page=page_number,
                    )

                ctx.logger.debug(
                    "page_extracted",
                    page=page_number,
                    blocks=len(text_blocks),
                    images=len(images),
                    chars=char_count,
                )
        finally:
            doc.close()

        ctx.logger.info(
            "extraction_complete",
            pages=manifest.page_count,
            image_extraction_failures=total_image_failures,
        )
