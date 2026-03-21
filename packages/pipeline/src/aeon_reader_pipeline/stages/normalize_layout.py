"""Stage 3 — normalize extracted primitives into canonical page layout."""

from __future__ import annotations

from aeon_reader_pipeline.config.patch_applier import apply_patches
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    NormalizedBBox,
    RegionCandidate,
)
from aeon_reader_pipeline.models.extract_models import BBox, ExtractedPage, TextBlock
from aeon_reader_pipeline.models.ir_models import (
    Block,
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    HeadingBlock,
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageAnchor,
    PageRecord,
    ParagraphBlock,
    TableBlock,
    TableCell,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.ids import (
    anchor_id,
    block_id,
    list_item_id,
    page_fingerprint,
)
from aeon_reader_pipeline.utils.normalization import (
    detect_body_font_size,
    is_likely_heading,
    is_noise_block,
    is_standalone_label,
    is_toc_entry,
    normalize_text,
    strip_bullet,
    strip_page_number_prefix,
)

STAGE_NAME = "normalize_layout"
STAGE_VERSION = "1.0.0"


def _collect_font_sizes(page: ExtractedPage) -> list[float]:
    """Collect all font sizes from spans on a page."""
    sizes: list[float] = []
    for block in page.text_blocks:
        for line in block.lines:
            for span in line.spans:
                sizes.append(span.font.size)
    return sizes


def _dedup_overlapping_lines(lines: list[str]) -> list[str]:
    """Remove overlapping line prefixes from PDF cascade/shadow text.

    Detects when line N starts with the suffix of line N-1 and keeps
    only the non-overlapping portion.
    """
    if len(lines) < 2:
        return lines
    result = [lines[0]]
    for line in lines[1:]:
        prev = result[-1]
        # Check if line starts with a suffix of prev
        best_overlap = 0
        for k in range(1, min(len(prev), len(line)) + 1):
            if prev.endswith(line[:k]):
                best_overlap = k
        if best_overlap > 2:
            # Keep only the non-overlapping part
            new_part = line[best_overlap:].strip()
            if new_part:
                result[-1] = prev + " " + new_part
        else:
            result.append(line)
    return result


def _block_text(block: TextBlock) -> str:
    """Get full normalized text of a text block."""
    parts: list[str] = []
    for line in block.lines:
        line_text = "".join(span.text for span in line.spans)
        normalized = normalize_text(line_text)
        if normalized:
            parts.append(normalized)
    parts = _dedup_overlapping_lines(parts)
    # Apply decorative marker stripping on the joined result
    # (markers like { } * may span across lines)
    joined = " ".join(parts)
    return normalize_text(joined)


def _block_font_size(block: TextBlock) -> float:
    """Get the dominant font size in a block."""
    sizes: list[float] = []
    for line in block.lines:
        for span in line.spans:
            sizes.append(span.font.size)
    if not sizes:
        return 0.0
    from collections import Counter

    return Counter(sizes).most_common(1)[0][0]


def _block_is_bold(block: TextBlock) -> bool:
    """Check if the majority of text in a block is bold."""
    bold_chars = 0
    total_chars = 0
    for line in block.lines:
        for span in line.spans:
            chars = len(span.text)
            total_chars += chars
            if span.font.is_bold:
                bold_chars += chars
    return total_chars > 0 and bold_chars / total_chars > 0.5


def _font_family(name: str) -> str:
    """Extract base font family, ignoring weight/style suffixes."""
    # "Adonis-Bold-SC700" -> "Adonis", "Adonis-Regular" -> "Adonis"
    return name.split("-")[0] if "-" in name else name


def _make_text_runs(block: TextBlock) -> list[InlineNode]:
    """Convert a TextBlock's spans into TextRun inline nodes.

    Merges adjacent spans that share the same font family and formatting
    but differ in size (common with small-caps styling in PDFs where the
    first letter is full-size and the rest is smaller).
    """
    runs: list[InlineNode] = []
    for line in block.lines:
        for span in line.spans:
            text = normalize_text(span.text)
            if not text:
                continue
            font = span.font
            # Try to merge with previous run if same family + formatting
            if runs:
                prev = runs[-1]
                assert isinstance(prev, TextRun)
                if (
                    prev.font_name is not None
                    and _font_family(prev.font_name) == _font_family(font.name)
                    and prev.bold == font.is_bold
                    and prev.italic == font.is_italic
                    and prev.monospace == font.is_monospace
                ):
                    merged_size = max(
                        prev.font_size or 0.0,
                        font.size,
                    )
                    runs[-1] = TextRun(
                        text=prev.text + text,
                        bold=prev.bold,
                        italic=prev.italic,
                        monospace=prev.monospace,
                        font_name=prev.font_name,
                        font_size=merged_size,
                    )
                    continue
            runs.append(
                TextRun(
                    text=text,
                    bold=font.is_bold,
                    italic=font.is_italic,
                    monospace=font.is_monospace,
                    font_name=font.name,
                    font_size=font.size,
                )
            )
    return runs


def _is_caption_text(text: str) -> bool:
    """Heuristic: does this text look like a figure/table caption?"""
    from aeon_reader_pipeline.utils.normalization import is_caption_text

    return is_caption_text(text)


def _classify_blocks(  # noqa: C901, PLR0915
    page: ExtractedPage,
    ctx: StageContext,
) -> list[Block]:
    """Classify extracted text blocks into semantic IR blocks."""
    doc_id = ctx.doc_id
    page_num = page.page_number
    rule = ctx.rule_profile

    all_sizes = _collect_font_sizes(page)
    body_size = detect_body_font_size(all_sizes)
    bullet_patterns = rule.list_detection.bullet_patterns
    min_ratio = rule.heading_detection.min_font_size_ratio
    max_heading_len = rule.heading_detection.max_heading_length

    blocks: list[Block] = []
    pending_list_items: list[ListItemBlock] = []
    list_block_index: int | None = None
    noise_count = 0

    def _flush_list() -> None:
        nonlocal pending_list_items, list_block_index
        if pending_list_items and list_block_index is not None:
            bid = block_id(doc_id, page_num, list_block_index, "list")
            blocks.append(
                ListBlock(
                    block_id=bid,
                    items=pending_list_items,
                    source_block_index=list_block_index,
                )
            )
            pending_list_items = []
            list_block_index = None

    # Add figure blocks for images
    for img in page.images:
        bid = block_id(doc_id, page_num, 900 + img.image_index, "figure")
        blocks.append(
            FigureBlock(
                block_id=bid,
                asset_ref=img.stored_as or img.content_hash[:16],
                alt_text="",
                source_block_index=900 + img.image_index,
            )
        )

    # Add table blocks from extracted tables
    for tbl in page.tables:
        bid = block_id(doc_id, page_num, 800 + tbl.table_index, "table")
        cells = [
            TableCell(
                row=c.row,
                col=c.col,
                text=c.text,
                row_span=c.row_span,
                col_span=c.col_span,
            )
            for c in tbl.cells
        ]
        blocks.append(
            TableBlock(
                block_id=bid,
                rows=tbl.rows,
                cols=tbl.cols,
                cells=cells,
                source_block_index=800 + tbl.table_index,
            )
        )

    for text_block in page.text_blocks:
        text = _block_text(text_block)
        if not text:
            continue
        # Skip page headers (e.g. "3 Introduction" or "3Introduction")
        if strip_page_number_prefix(text) != text:
            continue
        if is_noise_block(text):
            ctx.logger.debug(
                "noise_block_filtered",
                page=page_num,
                block_index=text_block.block_index,
                text=text[:80],
            )
            noise_count += 1
            continue

        font_size = _block_font_size(text_block)
        idx = text_block.block_index

        # Check for list item
        bullet, rest = strip_bullet(text, bullet_patterns)
        if bullet:
            if list_block_index is None:
                list_block_index = idx
            item_idx = len(pending_list_items)
            li_id = list_item_id(doc_id, page_num, list_block_index, item_idx)
            pending_list_items.append(
                ListItemBlock(
                    block_id=li_id,
                    bullet=bullet,
                    content=[TextRun(text=rest)],
                    source_block_index=idx,
                )
            )
            continue

        # Flush any pending list
        _flush_list()

        # Check for caption
        if _is_caption_text(text):
            bid = block_id(doc_id, page_num, idx, "caption")
            blocks.append(
                CaptionBlock(
                    block_id=bid,
                    content=_make_text_runs(text_block),
                    source_block_index=idx,
                )
            )
            continue

        # Check for heading
        if not is_toc_entry(text) and (
            is_likely_heading(
                text,
                font_size,
                body_size,
                min_ratio=min_ratio,
                max_length=max_heading_len,
            )
            or (
                _block_is_bold(text_block) and len(text) < max_heading_len and font_size > body_size
            )
        ):
            level = 1 if font_size >= body_size * 1.5 else 2
            bid = block_id(doc_id, page_num, idx, "heading")
            aid = anchor_id(doc_id, page_num, text)
            blocks.append(
                HeadingBlock(
                    block_id=bid,
                    level=level,
                    content=_make_text_runs(text_block),
                    anchor=aid,
                    source_block_index=idx,
                )
            )
            continue

        # Default: paragraph
        bid = block_id(doc_id, page_num, idx, "paragraph")
        blocks.append(
            ParagraphBlock(
                block_id=bid,
                content=_make_text_runs(text_block),
                source_block_index=idx,
            )
        )

    _flush_list()

    if noise_count > 0:
        ctx.logger.info(
            "noise_blocks_filtered",
            page=page_num,
            count=noise_count,
        )

    return blocks


def _should_merge_into_next(text: str) -> bool:
    """Check if this paragraph text looks like a continuation fragment."""
    stripped = text.strip()
    if not stripped:
        return True
    # Standalone labels (title-case, all-caps, single capitalized word)
    # should never be merged — they are UI terms or section headers.
    if is_standalone_label(stripped):
        return False
    # Short fragments
    if len(stripped) < 10:
        return True
    # Ends with hyphen (word break across lines)
    if stripped.endswith("-"):
        return True
    # Starts with lowercase (continuation of previous sentence)
    if stripped[0].islower():
        return True
    # Doesn't end with sentence-ending punctuation
    return stripped[-1] not in ".!?:;)\"'"


def _merge_small_paragraphs(blocks: list[Block]) -> list[Block]:
    """Merge consecutive paragraph fragments into coherent blocks.

    Detects continuation patterns: short text, trailing hyphens,
    lowercase starts, and missing sentence-ending punctuation.
    """
    if len(blocks) < 2:
        return blocks

    merged: list[Block] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if not isinstance(block, ParagraphBlock):
            merged.append(block)
            i += 1
            continue

        block_text = "".join(n.text for n in block.content if isinstance(n, TextRun))

        if _should_merge_into_next(block_text) and i + 1 < len(blocks):
            next_block = blocks[i + 1]
            if isinstance(next_block, ParagraphBlock):
                separator = [TextRun(text=" ")] if block.content else []
                combined = list(block.content) + separator + list(next_block.content)
                blocks[i + 1] = next_block.model_copy(update={"content": combined})
                i += 1
                continue

        merged.append(block)
        i += 1
    return merged


def _dedup_repeated_words(text: str) -> str:
    """Remove consecutive repeated word sequences from text.

    Handles PDF shadow/outline effects: 'Do not Do not open open' → 'Do not open'
    Tries phrase lengths from longest to shortest.
    """
    words = text.split()
    if len(words) < 2:
        return text
    result: list[str] = []
    i = 0
    while i < len(words):
        # Try to match repeated sequences of decreasing length
        matched = False
        for seq_len in range(min(4, (len(words) - i) // 2), 0, -1):
            seq = words[i : i + seq_len]
            nxt = words[i + seq_len : i + seq_len * 2]
            if seq == nxt:
                result.extend(seq)
                i += seq_len * 2
                matched = True
                break
        if not matched:
            result.append(words[i])
            i += 1
    return " ".join(result)


def _clean_block_content(blocks: list[Block]) -> list[Block]:
    """Post-process block content to fix issues spanning multiple text runs.

    Consolidates all TextRuns in each block into a single run with
    cleaned text — handles decorative markers, overlapping text, etc.
    """
    _content_kinds = (HeadingBlock, ParagraphBlock, CaptionBlock)
    result: list[Block] = []
    for block in blocks:
        if isinstance(block, _content_kinds):
            runs = [n for n in block.content if isinstance(n, TextRun)]
            if runs:
                full_text = " ".join(r.text for r in runs)
                cleaned = normalize_text(full_text)
                # Deduplicate repeated words in headings (PDF shadow effects)
                if isinstance(block, HeadingBlock):
                    cleaned = _dedup_repeated_words(cleaned)
                if cleaned:
                    merged_run = TextRun(
                        text=cleaned,
                        bold=runs[0].bold,
                        italic=runs[0].italic,
                        monospace=runs[0].monospace,
                        font_name=runs[0].font_name,
                        font_size=runs[0].font_size,
                    )
                    block = block.model_copy(update={"content": [merged_run]})
        result.append(block)
    return result


def _normalize_extract_bbox(
    bbox: BBox,
    width_pt: float,
    height_pt: float,
) -> NormalizedBBox:
    """Convert a PDF-point BBox to normalized [0,1] coordinates."""
    return NormalizedBBox(
        x0=max(0.0, min(1.0, bbox.x0 / width_pt)) if width_pt > 0 else 0.0,
        y0=max(0.0, min(1.0, bbox.y0 / height_pt)) if height_pt > 0 else 0.0,
        x1=max(0.0, min(1.0, bbox.x1 / width_pt)) if width_pt > 0 else 0.0,
        y1=max(0.0, min(1.0, bbox.y1 / height_pt)) if height_pt > 0 else 0.0,
    )


def _bbox_center_within(inner: NormalizedBBox, outer: NormalizedBBox) -> bool:
    """Check if the center of inner bbox falls within outer bbox."""
    cx = (inner.x0 + inner.x1) / 2
    cy = (inner.y0 + inner.y1) / 2
    return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1


def _assign_blocks_to_callouts(
    page: ExtractedPage,
    callout_regions: list[RegionCandidate],
) -> tuple[dict[str, list[int]], set[int]]:
    """Map callout regions to text block indices by spatial containment.

    Returns (callout_members, wrapped_indices) where callout_members
    maps region_id → list of block indices, and wrapped_indices is the
    union of all matched block indices.
    """
    block_norm_bboxes: dict[int, NormalizedBBox] = {}
    for tb in page.text_blocks:
        block_norm_bboxes[tb.block_index] = _normalize_extract_bbox(
            tb.bbox, page.width_pt, page.height_pt
        )

    callout_members: dict[str, list[int]] = {}
    wrapped_indices: set[int] = set()
    for region in callout_regions:
        members = [
            idx
            for idx, norm_bbox in block_norm_bboxes.items()
            if _bbox_center_within(norm_bbox, region.bbox)
        ]
        if members:
            callout_members[region.region_id] = members
            wrapped_indices.update(members)
    return callout_members, wrapped_indices


def _build_callout_block(
    member_indices: list[int],
    blocks_by_source: dict[int, list[Block]],
    doc_id: str,
    page_number: int,
) -> CalloutBlock | None:
    """Collect content from member blocks into a single CalloutBlock."""
    callout_content: list[InlineNode] = []
    for midx in sorted(member_indices):
        for member_block in blocks_by_source.get(midx, []):
            if hasattr(member_block, "content"):
                callout_content.extend(member_block.content)
    if not callout_content:
        return None
    bid = block_id(doc_id, page_number, min(member_indices), "callout")
    return CalloutBlock(
        block_id=bid,
        callout_type="note",
        content=callout_content,
        source_block_index=min(member_indices),
    )


def _wrap_callout_blocks(
    blocks: list[Block],
    page: ExtractedPage,
    callout_regions: list[RegionCandidate],
    doc_id: str,
) -> list[Block]:
    """Wrap blocks that fall within callout regions into CalloutBlocks.

    Uses spatial overlap between ExtractedPage text block bboxes and
    callout region bboxes to identify which blocks belong to a callout.
    Matched blocks are collected into a single CalloutBlock per region;
    unmatched blocks pass through unchanged.
    """
    if not callout_regions:
        return blocks

    callout_members, wrapped_indices = _assign_blocks_to_callouts(page, callout_regions)
    if not wrapped_indices:
        return blocks

    # Build index of source_block_index → classified blocks
    blocks_by_source: dict[int, list[Block]] = {}
    for block in blocks:
        src_idx = getattr(block, "source_block_index", None)
        if src_idx is not None:
            blocks_by_source.setdefault(src_idx, []).append(block)

    # Build result: insert CalloutBlocks at first occurrence, skip wrapped blocks
    result: list[Block] = []
    emitted_callouts: set[str] = set()
    for block in blocks:
        src_idx = getattr(block, "source_block_index", None)
        if src_idx is not None and src_idx in wrapped_indices:
            region_id = _find_callout_for_block(src_idx, callout_members, emitted_callouts)
            if region_id is not None:
                emitted_callouts.add(region_id)
                cb = _build_callout_block(
                    callout_members[region_id], blocks_by_source, doc_id, page.page_number
                )
                if cb is not None:
                    result.append(cb)
            continue
        result.append(block)
    return result


def _find_callout_for_block(
    src_idx: int,
    callout_members: dict[str, list[int]],
    emitted: set[str],
) -> str | None:
    """Find the callout region that contains this block index, if not yet emitted."""
    for region_id, member_indices in callout_members.items():
        if src_idx in member_indices and region_id not in emitted:
            return region_id
    return None


def _build_anchors(blocks: list[Block]) -> list[PageAnchor]:
    """Extract anchors from heading blocks."""
    anchors: list[PageAnchor] = []
    for b in blocks:
        if isinstance(b, HeadingBlock) and b.anchor:
            label = "".join(run.text for run in b.content if isinstance(run, TextRun))
            anchors.append(PageAnchor(anchor_id=b.anchor, block_id=b.block_id, label=label))
    return anchors


def _blocks_text_for_fingerprint(blocks: list[Block]) -> str:
    """Concatenate all text from blocks for fingerprinting."""
    parts: list[str] = []
    for b in blocks:
        if hasattr(b, "content"):
            for node in b.content:
                if isinstance(node, TextRun):
                    parts.append(node.text)
        if isinstance(b, ListBlock):
            for item in b.items:
                for node in item.content:
                    if isinstance(node, TextRun):
                        parts.append(node.text)
    return " ".join(parts)


@register_stage
class NormalizeLayoutStage(BaseStage):
    """Convert extracted primitives into semantic PageRecords."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Classify extracted blocks into headings, paragraphs, lists, figures, captions"

    def _load_callout_regions(
        self,
        ctx: StageContext,
        page_number: int,
    ) -> list[RegionCandidate]:
        """Load callout regions from canonical evidence (v3 only)."""
        if ctx.pipeline_config.architecture != "v3":
            return []
        try:
            canonical = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "collect_evidence",
                f"evidence/p{page_number:04d}_canonical.json",
                CanonicalPageEvidence,
            )
        except FileNotFoundError:
            return []
        if not canonical.has_callouts or canonical.region_graph is None:
            return []
        return [r for r in canonical.region_graph.regions if r.kind_hint == "callout"]

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        from aeon_reader_pipeline.utils.page_filter import pages_to_process

        page_nums = pages_to_process(manifest.page_count, ctx.pipeline_config.page_filter)
        ctx.logger.info("normalizing_layout", page_count=len(page_nums))

        for page_num in page_nums:
            extracted = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "extract_primitives",
                f"pages/p{page_num:04d}.json",
                ExtractedPage,
            )

            blocks = _classify_blocks(extracted, ctx)
            blocks = _merge_small_paragraphs(blocks)
            blocks = _clean_block_content(blocks)

            # Wrap blocks within callout regions (v3 evidence-driven)
            callout_regions = self._load_callout_regions(ctx, page_num)
            if callout_regions:
                blocks = _wrap_callout_blocks(blocks, extracted, callout_regions, ctx.doc_id)

            anchors = _build_anchors(blocks)
            fp = page_fingerprint(_blocks_text_for_fingerprint(blocks), page_num)

            record = PageRecord(
                page_number=page_num,
                doc_id=ctx.doc_id,
                width_pt=extracted.width_pt,
                height_pt=extracted.height_pt,
                blocks=blocks,
                anchors=anchors,
                source_pdf_sha256=extracted.source_pdf_sha256,
                fingerprint=fp,
            )

            # Apply patches (override block kinds, render modes, etc.)
            record = apply_patches(record, ctx.patch_set)

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{page_num:04d}.json",
                record,
            )

            ctx.logger.debug(
                "page_normalized",
                page=page_num,
                blocks=len(blocks),
                anchors=len(anchors),
            )

        ctx.logger.info("normalization_complete", pages=len(page_nums))
