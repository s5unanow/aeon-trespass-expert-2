"""Stage 5 — plan translation by segmenting content into translation units."""

from __future__ import annotations

from aeon_reader_pipeline.models.config_models import GlossaryPack, GlossaryTermEntry
from aeon_reader_pipeline.models.ir_models import (
    Block,
    CalloutBlock,
    CaptionBlock,
    HeadingBlock,
    ListBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslationPlan,
    TranslationPlanSummary,
    TranslationUnit,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.utils.ids import content_fingerprint, inline_id, unit_id
from aeon_reader_pipeline.utils.normalization import is_standalone_label

# Block types that have a `content` field with InlineNode items
_ContentBlock = HeadingBlock | ParagraphBlock | CaptionBlock | CalloutBlock

STAGE_NAME = "plan_translation"
STAGE_VERSION = "1.0.0"

# Default value moved to PipelineConfig.max_nodes_per_unit
# Kept as module-level fallback for _plan_page when called outside a stage
_DEFAULT_MAX_NODES_PER_UNIT = 20


def _extract_text_from_block(block: Block) -> str:
    """Get concatenated text from a block's content."""
    if not hasattr(block, "content"):
        return ""
    parts: list[str] = []
    for node in block.content:
        if isinstance(node, TextRun):
            parts.append(node.text)
    return " ".join(parts)


def _block_has_text(block: Block) -> bool:
    """Check if a block contains translatable text nodes."""
    if isinstance(block, ListBlock):
        return any(
            any(isinstance(n, TextRun) and n.text.strip() for n in item.content)
            for item in block.items
        )
    if isinstance(block, _ContentBlock):
        return any(isinstance(n, TextRun) and n.text.strip() for n in block.content)
    return False


def _style_hint_for_block(block: Block) -> str:
    """Derive a style hint from block kind."""
    if isinstance(block, HeadingBlock):
        return "heading"
    if isinstance(block, CaptionBlock):
        return "caption"
    if isinstance(block, ListBlock):
        return "list"
    return "paragraph"


def _collect_text_nodes(block: Block, block_id_str: str) -> list[TextNode]:
    """Extract TextNode entries from a block's inline content.

    Merges all TextRun nodes within a content block into a single TextNode
    so the LLM translates complete sentences rather than fragments.
    List items are kept separate (each item is its own sentence).
    """
    if isinstance(block, ListBlock):
        nodes: list[TextNode] = []
        for item in block.items:
            texts = [
                node.text
                for node in item.content
                if isinstance(node, TextRun) and node.text.strip()
            ]
            if texts:
                iid = inline_id(item.block_id, 0)
                nodes.append(TextNode(inline_id=iid, source_text=" ".join(texts)))
        return nodes

    if not isinstance(block, _ContentBlock):
        return []

    texts = [node.text for node in block.content if isinstance(node, TextRun) and node.text.strip()]
    if not texts:
        return []

    iid = inline_id(block_id_str, 0)
    return [TextNode(inline_id=iid, source_text=" ".join(texts))]


def _find_relevant_glossary(
    text_nodes: list[TextNode],
    glossary_pack: GlossaryPack,
    doc_id: str,
) -> list[GlossaryHint]:
    """Find glossary terms that appear in the given text nodes."""
    if not glossary_pack.terms:
        return []

    combined_text = " ".join(n.source_text.lower() for n in text_nodes)
    hints: list[GlossaryHint] = []
    seen: set[str] = set()

    for term in glossary_pack.terms:
        if not _term_applies_to_doc(term, doc_id):
            continue

        matches = term.en_canonical.lower() in combined_text or any(
            alias.lower() in combined_text for alias in term.en_aliases
        )
        if matches and term.term_id not in seen:
            seen.add(term.term_id)
            hints.append(
                GlossaryHint(
                    en=term.en_canonical,
                    ru=term.ru_preferred,
                    locked=term.lock_translation,
                )
            )
    return hints


def _term_applies_to_doc(term: GlossaryTermEntry, doc_id: str) -> bool:
    """Check if a glossary term applies to this document."""
    if not term.doc_scope:
        return True
    return "*" in term.doc_scope or doc_id in term.doc_scope


def _get_section_path(record: PageRecord, block_index: int) -> list[str]:
    """Find section headings preceding this block."""
    path: list[str] = []
    for b in record.blocks[:block_index]:
        if isinstance(b, HeadingBlock):
            text = _extract_text_from_block(b)
            if text:
                if b.level == 1:
                    path = [text]
                else:
                    path.append(text)
    return path


def _plan_page(  # noqa: C901, PLR0915
    record: PageRecord,
    doc_id: str,
    glossary_pack: GlossaryPack,
    max_nodes_per_unit: int = _DEFAULT_MAX_NODES_PER_UNIT,
    context_window_chars: int = 200,
) -> list[TranslationUnit]:
    """Segment a page into translation units."""
    if record.render_mode == "facsimile":
        return []

    units: list[TranslationUnit] = []
    unit_index = 0

    pending_blocks: list[tuple[int, Block]] = []
    pending_nodes: list[TextNode] = []
    pending_block_ids: list[str] = []

    def _flush_unit(style: str, section: list[str]) -> None:
        nonlocal unit_index, pending_blocks, pending_nodes, pending_block_ids
        if not pending_nodes:
            pending_blocks = []
            pending_block_ids = []
            return

        uid = unit_id(doc_id, record.page_number, unit_index)
        source_text = " ".join(n.source_text for n in pending_nodes)
        fp = content_fingerprint(source_text)
        glossary = _find_relevant_glossary(pending_nodes, glossary_pack, doc_id)

        units.append(
            TranslationUnit(
                unit_id=uid,
                doc_id=doc_id,
                page_number=record.page_number,
                block_ids=list(pending_block_ids),
                section_path=list(section),
                style_hint=style,
                glossary_subset=glossary,
                text_nodes=list(pending_nodes),
                source_fingerprint=fp,
            )
        )
        unit_index += 1
        pending_blocks = []
        pending_nodes = []
        pending_block_ids = []

    for block_idx, block in enumerate(record.blocks):
        if not _block_has_text(block):
            continue

        nodes = _collect_text_nodes(block, block.block_id)
        if not nodes:
            continue

        style = _style_hint_for_block(block)
        section = _get_section_path(record, block_idx)

        # Headings always get their own unit
        if isinstance(block, HeadingBlock):
            _flush_unit(
                _style_hint_for_block(pending_blocks[0][1]) if pending_blocks else "paragraph",
                _get_section_path(record, pending_blocks[0][0]) if pending_blocks else [],
            )
            pending_nodes = nodes
            pending_block_ids = [block.block_id]
            pending_blocks = [(block_idx, block)]
            _flush_unit(style, section)
            continue

        # Lists get their own unit
        if isinstance(block, ListBlock):
            _flush_unit(
                _style_hint_for_block(pending_blocks[0][1]) if pending_blocks else "paragraph",
                _get_section_path(record, pending_blocks[0][0]) if pending_blocks else [],
            )
            pending_nodes = nodes
            pending_block_ids = [block.block_id]
            pending_blocks = [(block_idx, block)]
            _flush_unit(style, section)
            continue

        # Standalone labels get their own unit (UI terms, section headers)
        block_text = " ".join(n.source_text for n in nodes)
        if is_standalone_label(block_text):
            _flush_unit(
                _style_hint_for_block(pending_blocks[0][1]) if pending_blocks else "paragraph",
                _get_section_path(record, pending_blocks[0][0]) if pending_blocks else [],
            )
            pending_nodes = nodes
            pending_block_ids = [block.block_id]
            pending_blocks = [(block_idx, block)]
            _flush_unit(style, section)
            continue

        # Would adding this block exceed the node limit?
        if len(pending_nodes) + len(nodes) > max_nodes_per_unit:
            _flush_unit(
                _style_hint_for_block(pending_blocks[0][1]) if pending_blocks else "paragraph",
                _get_section_path(record, pending_blocks[0][0]) if pending_blocks else [],
            )

        pending_blocks.append((block_idx, block))
        pending_nodes.extend(nodes)
        pending_block_ids.append(block.block_id)

    # Flush remaining
    if pending_nodes:
        _flush_unit(
            _style_hint_for_block(pending_blocks[0][1]) if pending_blocks else "paragraph",
            _get_section_path(record, pending_blocks[0][0]) if pending_blocks else [],
        )

    # Add context_before / context_after
    for i, u in enumerate(units):
        if i > 0:
            prev_text = " ".join(n.source_text for n in units[i - 1].text_nodes)
            u_copy = u.model_copy(update={"context_before": prev_text[:context_window_chars]})
            units[i] = u_copy
        if i < len(units) - 1:
            next_text = " ".join(n.source_text for n in units[i + 1].text_nodes)
            u_copy = units[i].model_copy(update={"context_after": next_text[:context_window_chars]})
            units[i] = u_copy

    return units


@register_stage
class PlanTranslationStage(BaseStage):
    """Segment resolved pages into bounded translation units."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Plan translation by segmenting content into translation units"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        ctx.logger.info("planning_translation", page_count=manifest.page_count)

        all_units: list[TranslationUnit] = []
        skipped_pages: list[int] = []

        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "resolve_assets_symbols",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )

            if record.render_mode == "facsimile":
                skipped_pages.append(page_num)
                ctx.logger.debug("page_skipped_facsimile", page=page_num)
                continue

            page_units = _plan_page(
                record,
                ctx.doc_id,
                ctx.glossary_pack,
                max_nodes_per_unit=ctx.pipeline_config.max_nodes_per_unit,
                context_window_chars=ctx.pipeline_config.context_window_chars,
            )
            all_units.extend(page_units)

            ctx.logger.debug(
                "page_planned",
                page=page_num,
                units=len(page_units),
            )

        # Write individual unit files
        for u in all_units:
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"units/{u.unit_id}.json",
                u,
            )

        # Write full plan
        plan = TranslationPlan(
            doc_id=ctx.doc_id,
            source_locale=ctx.document_config.source_locale,
            target_locale=ctx.document_config.target_locale,
            total_units=len(all_units),
            total_text_nodes=sum(len(u.text_nodes) for u in all_units),
            units=all_units,
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "translation_plan.json",
            plan,
        )

        # Write summary
        summary = TranslationPlanSummary(
            doc_id=ctx.doc_id,
            page_count=manifest.page_count,
            total_units=len(all_units),
            total_text_nodes=sum(len(u.text_nodes) for u in all_units),
            skipped_pages=skipped_pages,
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "summary.json",
            summary,
        )

        ctx.logger.info(
            "translation_plan_complete",
            total_units=len(all_units),
            total_text_nodes=sum(len(u.text_nodes) for u in all_units),
            skipped_pages=len(skipped_pages),
        )
