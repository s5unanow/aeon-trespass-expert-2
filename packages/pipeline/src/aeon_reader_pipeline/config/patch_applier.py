"""Apply PatchSet overrides to normalized page records."""

from __future__ import annotations

from typing import Literal

from aeon_reader_pipeline.models.config_models import PatchEntry, PatchSet
from aeon_reader_pipeline.models.ir_models import (
    Block,
    HeadingBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)


def apply_patches(record: PageRecord, patch_set: PatchSet | None) -> PageRecord:
    """Apply all matching patches to a PageRecord.

    Patches are applied in order. Each patch is declarative and idempotent.
    """
    if patch_set is None or not patch_set.patches:
        return record

    page_patches = [
        p for p in patch_set.patches if p.target_page is None or p.target_page == record.page_number
    ]

    if not page_patches:
        return record

    new_blocks = list(record.blocks)
    render_mode = record.render_mode
    fallback_image_ref = record.fallback_image_ref

    for patch in page_patches:
        if patch.action == "override_block_kind":
            new_blocks = _apply_override_block_kind(new_blocks, patch)
        elif patch.action == "set_render_mode":
            render_mode = _resolve_render_mode(patch)
            fallback_image_ref = _resolve_fallback_ref(patch, fallback_image_ref)
        elif patch.action == "force_fallback":
            render_mode = "facsimile"
            fallback_image_ref = _resolve_fallback_ref(patch, fallback_image_ref)
        elif patch.action == "replace_text":
            new_blocks = _apply_replace_text(new_blocks, patch)

    return record.model_copy(
        update={
            "blocks": new_blocks,
            "render_mode": render_mode,
            "fallback_image_ref": fallback_image_ref,
        }
    )


def _resolve_render_mode(
    patch: PatchEntry,
) -> Literal["semantic", "hybrid", "facsimile"]:
    """Extract validated render_mode from a set_render_mode patch."""
    mode = str(patch.payload.get("render_mode", "semantic"))
    if mode == "hybrid":
        return "hybrid"
    if mode == "facsimile":
        return "facsimile"
    return "semantic"


def _resolve_fallback_ref(patch: PatchEntry, current: str | None) -> str | None:
    """Extract fallback_image_ref from a patch payload if present."""
    ref = patch.payload.get("fallback_image_ref")
    return str(ref) if ref is not None else current


def _apply_override_block_kind(blocks: list[Block], patch: PatchEntry) -> list[Block]:
    """Change a block's kind (e.g. paragraph → heading)."""
    target = patch.target_block_id
    new_kind = patch.payload.get("new_kind", "")
    if not target or not new_kind:
        return blocks

    result: list[Block] = []
    for block in blocks:
        if block.block_id == target:
            block = _convert_block_kind(block, new_kind)
        result.append(block)
    return result


def _convert_block_kind(block: Block, new_kind: str) -> Block:
    """Convert a block to a different kind, preserving content where possible."""
    content = getattr(block, "content", [])

    if new_kind == "heading":
        level = 1
        return HeadingBlock(
            block_id=block.block_id,
            level=level,
            content=content,
            source_block_index=block.source_block_index,
        )
    elif new_kind == "paragraph":
        return ParagraphBlock(
            block_id=block.block_id,
            content=content,
            source_block_index=block.source_block_index,
        )
    # For unsupported conversions, return unchanged
    return block


def _apply_replace_text(blocks: list[Block], patch: PatchEntry) -> list[Block]:
    """Replace text content in a targeted block."""
    target = patch.target_block_id
    new_text = patch.payload.get("text", "")
    if not target:
        return blocks

    result: list[Block] = []
    for block in blocks:
        if block.block_id == target and hasattr(block, "content"):
            block = block.model_copy(update={"content": [TextRun(text=new_text)]})
        result.append(block)
    return result
