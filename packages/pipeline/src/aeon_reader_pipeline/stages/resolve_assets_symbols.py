"""Stage 4 — resolve asset references and map symbols to icon definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    PageFigureCaptionLinks,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    SymbolAnchorType,
)
from aeon_reader_pipeline.models.ir_models import (
    Block,
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
from aeon_reader_pipeline.utils.figure_caption_linking import (
    apply_links_to_blocks,
    link_figures_captions_sequential,
    link_figures_captions_spatial,
)

STAGE_NAME = "resolve_assets_symbols"
STAGE_VERSION = "1.2.0"


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


def _apply_evidence_candidates(
    record: PageRecord,
    page_cands: PageSymbolCandidates,
    min_confidence: float,
) -> PageRecord:
    """Insert SymbolRef nodes for pre-classified evidence candidates.

    Only applies candidates that are classified and above the confidence
    threshold. Text-token candidates are skipped here since the legacy
    text-splitting path already handles them. Raster/vector candidates
    annotate matching figure blocks with symbol metadata.
    """
    if not page_cands.candidates:
        return record

    # Collect classified non-text-token symbols above threshold.
    # Use highest-confidence candidate when multiple match the same primitive.
    evidence_symbols: dict[str, tuple[str, float, SymbolAnchorType]] = {}
    for cand in page_cands.candidates:
        if (
            cand.is_classified
            and cand.confidence >= min_confidence
            and cand.evidence_source != "text_token"
            and cand.symbol_id
            and cand.source_primitive_id
        ):
            existing = evidence_symbols.get(cand.source_primitive_id)
            if existing is None or cand.confidence > existing[1]:
                evidence_symbols[cand.source_primitive_id] = (
                    cand.symbol_id,
                    cand.confidence,
                    cand.anchor_type,
                )

    if not evidence_symbols:
        return record

    new_blocks: list[Block] = []
    for block in record.blocks:
        if isinstance(block, FigureBlock) and block.asset_ref:
            for prim_id, (sym_id, _conf, anchor) in evidence_symbols.items():
                if prim_id in (block.asset_ref, block.block_id):
                    # Preserve existing alt_text, prepend symbol tag with anchor
                    existing_alt = block.alt_text or ""
                    alt = f"[symbol:{sym_id}:{anchor}] {existing_alt}".strip()
                    block = block.model_copy(update={"alt_text": alt})
                    break
        new_blocks.append(block)

    return record.model_copy(update={"blocks": new_blocks})


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

        from aeon_reader_pipeline.utils.page_filter import pages_to_process

        page_nums = pages_to_process(manifest.page_count, ctx.pipeline_config.page_filter)
        ctx.logger.info("resolving_assets_symbols", page_count=len(page_nums))

        symbol_tokens = _build_symbol_token_map(ctx)
        min_confidence = ctx.rule_profile.symbol_detection.min_confidence
        all_assets: list[ResolvedAsset] = []

        for page_num in page_nums:
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "normalize_layout",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )

            # Link figures to captions using spatial evidence
            fig_cap_links = self._compute_figure_caption_links(ctx, record, page_num)
            record = apply_links_to_blocks(record, fig_cap_links)

            # Persist linkage artifact for review
            ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"pages/p{page_num:04d}_figure_caption_links.json",
                fig_cap_links,
            )

            # Resolve symbol tokens in text
            record = _resolve_symbols_in_page(record, symbol_tokens)

            # Consume pre-classified evidence candidates
            page_cands = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "collect_evidence",
                f"evidence/p{page_num:04d}_symbol_candidates.json",
                PageSymbolCandidates,
            )
            record = _apply_evidence_candidates(record, page_cands, min_confidence)

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
                fig_caption_links=len(fig_cap_links.links),
                link_method=fig_cap_links.method,
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

    def _compute_figure_caption_links(
        self,
        ctx: StageContext,
        record: PageRecord,
        page_num: int,
    ) -> PageFigureCaptionLinks:
        """Link figures to captions using spatial evidence."""
        canonical = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "collect_evidence",
            f"evidence/p{page_num:04d}_canonical.json",
            CanonicalPageEvidence,
        )
        if canonical.region_graph is not None:
            primitive = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "collect_evidence",
                f"evidence/p{page_num:04d}_primitive.json",
                PrimitivePageEvidence,
            )
            return link_figures_captions_spatial(canonical.region_graph, primitive, record)

        return link_figures_captions_sequential(record)
