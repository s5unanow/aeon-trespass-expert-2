"""Stage 4 — resolve asset references and map symbols to icon definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.ir_models import (
    Block,
    CaptionBlock,
    FigureBlock,
    InlineNode,
    PageRecord,
    SymbolRef,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "resolve_assets_symbols"
STAGE_VERSION = "1.0.0"


class ResolvedAsset(BaseModel):
    """A resolved asset record with source and render metadata."""

    asset_id: str
    source_file: str
    content_hash: str = ""
    width: int = 0
    height: int = 0
    alt_text: str = ""
    page_number: int = 0
    figure_block_id: str = ""
    caption_block_id: str | None = None
    render_policy: str = "inline"


class AssetManifest(BaseModel):
    """Collection of all resolved assets for a document."""

    doc_id: str
    assets: list[ResolvedAsset] = Field(default_factory=list)


def _link_figures_to_captions(record: PageRecord) -> dict[str, str]:
    """Link figure blocks to their nearest following caption block.

    Returns a mapping of figure_block_id → caption_block_id.
    """
    links: dict[str, str] = {}
    blocks = record.blocks
    for i, block in enumerate(blocks):
        if isinstance(block, FigureBlock):
            # Look for a caption block immediately after
            for j in range(i + 1, min(i + 3, len(blocks))):
                candidate = blocks[j]
                if isinstance(candidate, CaptionBlock):
                    links[block.block_id] = candidate.block_id
                    break
    return links


def _resolve_symbols_in_page(
    record: PageRecord,
    symbol_tokens: dict[str, str],
) -> PageRecord:
    """Scan text runs for symbol tokens and insert SymbolRef nodes.

    symbol_tokens maps token → symbol_id.
    """
    if not symbol_tokens:
        return record

    new_blocks: list[Block] = []
    for block in record.blocks:
        if not hasattr(block, "content"):
            new_blocks.append(block)
            continue

        new_content: list[InlineNode] = []
        for node in block.content:
            if isinstance(node, TextRun):
                resolved = _resolve_text_run(node, symbol_tokens)
                new_content.extend(resolved)
            else:
                new_content.append(node)

        updated: Block = block.model_copy(update={"content": new_content})
        new_blocks.append(updated)

    return record.model_copy(update={"blocks": new_blocks})


def _resolve_text_run(
    run: TextRun,
    symbol_tokens: dict[str, str],
) -> list[InlineNode]:
    """Split a text run at symbol token boundaries."""
    text = run.text
    result: list[InlineNode] = []

    for token, symbol_id in symbol_tokens.items():
        if token in text:
            parts = text.split(token, 1)
            if parts[0]:
                result.append(run.model_copy(update={"text": parts[0]}))
            result.append(SymbolRef(symbol_id=symbol_id, alt_text=token))
            text = parts[1]

    if text:
        if result:
            result.append(run.model_copy(update={"text": text}))
        else:
            result.append(run)

    return result if result else [run]


def _build_symbol_token_map(ctx: StageContext) -> dict[str, str]:
    """Build a mapping of text tokens → symbol IDs from the symbol pack."""
    token_map: dict[str, str] = {}
    for symbol in ctx.symbol_pack.symbols:
        for token in symbol.detection.text_tokens:
            token_map[token] = symbol.symbol_id
    return token_map


@register_stage
class ResolveAssetsSymbolsStage(BaseStage):
    """Resolve asset references and map inline symbols."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Link figures to captions, resolve symbols, create asset records"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        ctx.logger.info("resolving_assets_symbols", page_count=manifest.page_count)

        symbol_tokens = _build_symbol_token_map(ctx)
        all_assets: list[ResolvedAsset] = []

        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "normalize_layout",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )

            # Link figures to captions
            fig_caption_links = _link_figures_to_captions(record)

            # Update figure blocks with caption links
            new_blocks = []
            for block in record.blocks:
                if isinstance(block, FigureBlock) and block.block_id in fig_caption_links:
                    block = block.model_copy(
                        update={"caption_block_id": fig_caption_links[block.block_id]}
                    )
                if isinstance(block, CaptionBlock):
                    # Find parent figure
                    for fig_id, cap_id in fig_caption_links.items():
                        if cap_id == block.block_id:
                            block = block.model_copy(update={"parent_block_id": fig_id})
                            break
                new_blocks.append(block)

            record = record.model_copy(update={"blocks": new_blocks})

            # Resolve symbol tokens in text
            record = _resolve_symbols_in_page(record, symbol_tokens)

            # Collect asset records from figures
            for block in record.blocks:
                if isinstance(block, FigureBlock) and block.asset_ref:
                    all_assets.append(
                        ResolvedAsset(
                            asset_id=block.block_id,
                            source_file=block.asset_ref,
                            alt_text=block.alt_text,
                            page_number=page_num,
                            figure_block_id=block.block_id,
                            caption_block_id=block.caption_block_id,
                        )
                    )

            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{page_num:04d}.json",
                record,
            )

            ctx.logger.debug(
                "page_resolved",
                page=page_num,
                assets=len([b for b in record.blocks if isinstance(b, FigureBlock)]),
            )

        # Write asset manifest
        asset_manifest = AssetManifest(doc_id=ctx.doc_id, assets=all_assets)
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "assets.json",
            asset_manifest,
        )

        ctx.logger.info(
            "resolution_complete",
            pages=manifest.page_count,
            total_assets=len(all_assets),
        )
