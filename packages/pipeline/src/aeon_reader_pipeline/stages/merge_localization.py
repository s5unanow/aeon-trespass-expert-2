"""Stage 7 — merge translated units back into localized page records."""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import (
    Block,
    CalloutBlock,
    CaptionBlock,
    HeadingBlock,
    InlineNode,
    ListBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.translation_models import (
    TranslationPlan,
    TranslationResult,
    TranslationUnit,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "merge_localization"
STAGE_VERSION = "1.0.0"

# Block types that carry translatable inline content
_ContentBlock = HeadingBlock | ParagraphBlock | CaptionBlock | CalloutBlock


def _build_translation_map(
    units: list[TranslationUnit],
    results: list[TranslationResult],
) -> dict[str, str]:
    """Build inline_id → ru_text mapping from translation results.

    Only includes results that have matching units (by unit_id).
    """
    result_by_unit: dict[str, TranslationResult] = {r.unit_id: r for r in results}
    mapping: dict[str, str] = {}

    for unit in units:
        result = result_by_unit.get(unit.unit_id)
        if result is None:
            continue
        for t in result.translations:
            mapping[t.inline_id] = t.ru_text

    return mapping


def _merge_inline_translations(
    content: list[InlineNode],
    translation_map: dict[str, str],
    block_id: str,
) -> list[InlineNode]:
    """Inject ru_text into TextRun nodes that have translations.

    Supports merged mode: when plan_translation emitted a single merged
    TextNode (inline_id ending in :i000) for the whole block, we replace
    all TextRun nodes with a single TextRun containing the full translation.
    """
    # Check for merged translation (only :i000 exists for this block)
    merged_id = f"{block_id}:i000"
    merged_ru = translation_map.get(merged_id)

    has_individual = any(
        f"{block_id}:i{idx:03d}" in translation_map for idx in range(1, len(content))
    )

    if merged_ru is not None and not has_individual:
        # Merged mode: combine all source text and apply single translation
        source_parts = [
            node.text for node in content if isinstance(node, TextRun) and node.text.strip()
        ]
        full_source = " ".join(source_parts)
        return [TextRun(text=full_source, ru_text=merged_ru)]

    # Individual mode: original per-node matching
    merged: list[InlineNode] = []
    for idx, node in enumerate(content):
        if isinstance(node, TextRun):
            iid = f"{block_id}:i{idx:03d}"
            ru_text = translation_map.get(iid)
            if ru_text is not None:
                node = node.model_copy(update={"ru_text": ru_text})
        merged.append(node)
    return merged


def _merge_blocks(
    blocks: list[Block],
    translation_map: dict[str, str],
) -> list[Block]:
    """Merge translations into all blocks."""
    merged: list[Block] = []
    for block in blocks:
        if isinstance(block, ListBlock):
            new_items = []
            for item in block.items:
                new_content = _merge_inline_translations(
                    item.content, translation_map, item.block_id
                )
                new_items.append(item.model_copy(update={"content": new_content}))
            block = block.model_copy(update={"items": new_items})
        elif isinstance(block, _ContentBlock):
            new_content = _merge_inline_translations(block.content, translation_map, block.block_id)
            block = block.model_copy(update={"content": new_content})
        merged.append(block)
    return merged


def _load_results_for_page(
    ctx: StageContext,
    units: list[TranslationUnit],
) -> list[TranslationResult]:
    """Load translation results for units belonging to a page."""
    results: list[TranslationResult] = []
    for unit in units:
        try:
            result = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "translate_units",
                f"results/{unit.unit_id}.json",
                TranslationResult,
            )
            results.append(result)
        except FileNotFoundError:
            ctx.logger.warning("missing_translation_result", unit_id=unit.unit_id)
    return results


@register_stage
class MergeLocalizationStage(BaseStage):
    """Merge translations back into page records."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Inject translated text into localized page copies"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "plan_translation",
            "translation_plan.json",
            TranslationPlan,
        )

        ctx.logger.info(
            "merging_localization",
            page_count=manifest.page_count,
            units=plan.total_units,
        )

        # Group units by page
        units_by_page: dict[int, list[TranslationUnit]] = {}
        for unit in plan.units:
            units_by_page.setdefault(unit.page_number, []).append(unit)

        merged_count = 0
        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "resolve_assets_symbols",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )

            page_units = units_by_page.get(page_num, [])
            if not page_units:
                # No translations for this page — pass through unchanged
                ctx.artifact_store.write_artifact(
                    ctx.run_id,
                    ctx.doc_id,
                    STAGE_NAME,
                    f"pages/p{page_num:04d}.json",
                    record,
                )
                continue

            results = _load_results_for_page(ctx, page_units)
            translation_map = _build_translation_map(page_units, results)
            new_blocks = _merge_blocks(record.blocks, translation_map)

            localized = record.model_copy(update={"blocks": new_blocks})
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{page_num:04d}.json",
                localized,
            )

            merged_count += len(translation_map)
            ctx.logger.debug(
                "page_merged",
                page=page_num,
                translations=len(translation_map),
            )

        ctx.logger.info(
            "localization_merge_complete",
            pages=manifest.page_count,
            merged_translations=merged_count,
        )
