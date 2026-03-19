"""Stage 11 — export finalized content as a site bundle for the reader app.

Reads from apply_safe_fixes (10_fix) pages, enrich_content navigation/search/
summary, and evaluate_qa summary. Produces public BundlePage files and bundle
manifest under 11_export/site_bundle/<doc_id>/.
"""

from __future__ import annotations

import shutil

from aeon_reader_pipeline.models.ir_models import (
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    GlossaryRef,
    HeadingBlock,
    ListBlock,
    ListItemBlock,
    PageAnchor,
    PageRecord,
    ParagraphBlock,
    SymbolRef,
    TableBlock,
    TextRun,
)
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.qa_models import QASummary
from aeon_reader_pipeline.models.site_bundle_models import (
    BuildArtifact,
    BuildArtifacts,
    BundleAssetEntry,
    BundleCalloutBlock,
    BundleCaptionBlock,
    BundleDividerBlock,
    BundleFigureBlock,
    BundleGlossary,
    BundleGlossaryEntry,
    BundleGlossaryRef,
    BundleHeadingBlock,
    BundleListBlock,
    BundleListItemBlock,
    BundlePage,
    BundlePageAnchor,
    BundleParagraphBlock,
    BundleSymbolRef,
    BundleTableBlock,
    BundleTableCell,
    BundleTextRun,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.stages.enrich_content import (
    DocumentSummary,
    NavigationTree,
    SearchIndex,
)

STAGE_NAME = "export_site_bundle"
STAGE_VERSION = "1.0.0"

# Set during export to prefix asset paths
_export_doc_id: str = ""


# ---------------------------------------------------------------------------
# Conversion helpers — strip internal fields from IR models
# ---------------------------------------------------------------------------

_InlineSource = TextRun | SymbolRef | GlossaryRef

_BlockWithContent = HeadingBlock | ParagraphBlock | CaptionBlock | CalloutBlock


def _convert_inline(node: _InlineSource) -> BundleTextRun | BundleSymbolRef | BundleGlossaryRef:
    """Convert an internal inline node to its public bundle equivalent."""
    if isinstance(node, TextRun):
        return BundleTextRun(
            text=node.text,
            ru_text=node.ru_text,
            bold=node.bold,
            italic=node.italic,
            monospace=node.monospace,
        )
    if isinstance(node, SymbolRef):
        return BundleSymbolRef(
            symbol_id=node.symbol_id,
            alt_text=node.alt_text,
        )
    return BundleGlossaryRef(
        term_id=node.term_id,
        surface_form=node.surface_form,
        ru_surface_form=node.ru_surface_form,
    )


def _convert_inlines(
    nodes: list[_InlineSource],
) -> list[BundleTextRun | BundleSymbolRef | BundleGlossaryRef]:
    return [_convert_inline(n) for n in nodes]


def _convert_block(
    block: HeadingBlock
    | ParagraphBlock
    | ListBlock
    | ListItemBlock
    | FigureBlock
    | CaptionBlock
    | TableBlock
    | CalloutBlock
    | DividerBlock,
) -> (
    BundleHeadingBlock
    | BundleParagraphBlock
    | BundleListBlock
    | BundleListItemBlock
    | BundleFigureBlock
    | BundleCaptionBlock
    | BundleTableBlock
    | BundleCalloutBlock
    | BundleDividerBlock
):
    """Convert an internal block to its public bundle equivalent."""
    if isinstance(block, HeadingBlock):
        return BundleHeadingBlock(
            block_id=block.block_id,
            level=block.level,
            content=_convert_inlines(list(block.content)),
            anchor=block.anchor,
        )
    if isinstance(block, ParagraphBlock):
        return BundleParagraphBlock(
            block_id=block.block_id,
            content=_convert_inlines(list(block.content)),
        )
    if isinstance(block, ListBlock):
        return BundleListBlock(
            block_id=block.block_id,
            list_type=block.list_type,
            items=[
                BundleListItemBlock(
                    block_id=item.block_id,
                    bullet=item.bullet,
                    content=_convert_inlines(list(item.content)),
                )
                for item in block.items
            ],
        )
    if isinstance(block, ListItemBlock):
        return BundleListItemBlock(
            block_id=block.block_id,
            bullet=block.bullet,
            content=_convert_inlines(list(block.content)),
        )
    if isinstance(block, FigureBlock):
        return BundleFigureBlock(
            block_id=block.block_id,
            asset_ref=f"/assets/{_export_doc_id}/{block.asset_ref}" if block.asset_ref else "",
            alt_text=block.alt_text,
            caption_block_id=block.caption_block_id,
        )
    if isinstance(block, CaptionBlock):
        return BundleCaptionBlock(
            block_id=block.block_id,
            content=_convert_inlines(list(block.content)),
            parent_block_id=block.parent_block_id,
        )
    if isinstance(block, TableBlock):
        return BundleTableBlock(
            block_id=block.block_id,
            rows=block.rows,
            cols=block.cols,
            cells=[
                BundleTableCell(
                    row=c.row,
                    col=c.col,
                    text=c.text,
                    row_span=c.row_span,
                    col_span=c.col_span,
                )
                for c in block.cells
            ],
        )
    if isinstance(block, CalloutBlock):
        return BundleCalloutBlock(
            block_id=block.block_id,
            callout_type=block.callout_type,
            content=_convert_inlines(list(block.content)),
        )
    # DividerBlock
    return BundleDividerBlock(block_id=block.block_id)


def _convert_anchor(anchor: PageAnchor) -> BundlePageAnchor:
    return BundlePageAnchor(
        anchor_id=anchor.anchor_id,
        block_id=anchor.block_id,
        label=anchor.label,
    )


def convert_page_to_bundle(record: PageRecord) -> BundlePage:
    """Convert an internal PageRecord to a public BundlePage."""
    return BundlePage(
        page_number=record.page_number,
        doc_id=record.doc_id,
        width_pt=record.width_pt,
        height_pt=record.height_pt,
        render_mode=record.render_mode,
        blocks=[_convert_block(b) for b in record.blocks],
        anchors=[_convert_anchor(a) for a in record.anchors],
    )


def _export_glossary(
    ctx: StageContext,
    artifacts: list[BuildArtifact],
) -> bool:
    """Export glossary terms scoped to this document. Returns has_glossary."""
    glossary_terms = ctx.glossary_pack.terms if ctx.glossary_pack else []
    if not glossary_terms:
        return False
    doc_scope_terms = [t for t in glossary_terms if "*" in t.doc_scope or ctx.doc_id in t.doc_scope]
    if not doc_scope_terms:
        return False
    glossary = BundleGlossary(
        doc_id=ctx.doc_id,
        entries=[
            BundleGlossaryEntry(
                term_id=t.term_id,
                en_canonical=t.en_canonical,
                ru_preferred=t.ru_preferred,
                definition_ru=t.definition_ru,
                definition_en=t.definition_en,
            )
            for t in doc_scope_terms
        ],
        total_entries=len(doc_scope_terms),
    )
    glossary_path = ctx.artifact_store.write_artifact(
        ctx.run_id,
        ctx.doc_id,
        STAGE_NAME,
        f"site_bundle/{ctx.doc_id}/glossary.json",
        glossary,
    )
    artifacts.append(
        BuildArtifact(
            path="glossary.json",
            artifact_type="glossary",
            size_bytes=glossary_path.stat().st_size,
        )
    )
    ctx.logger.info("glossary_exported", term_count=len(doc_scope_terms))
    return True


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


@register_stage
class ExportSiteBundleStage(BaseStage):
    """Export finalized content as a public site bundle for the reader."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Export site bundle for reader consumption"

    def execute(self, ctx: StageContext) -> None:
        global _export_doc_id
        _export_doc_id = ctx.doc_id

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        ctx.logger.info(
            "exporting_site_bundle",
            page_count=manifest.page_count,
        )

        # Convert and write bundle pages (read from apply_safe_fixes)
        artifacts: list[BuildArtifact] = []
        for page_num in range(1, manifest.page_count + 1):
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "apply_safe_fixes",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )
            bundle_page = convert_page_to_bundle(record)
            path = ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"site_bundle/{ctx.doc_id}/pages/p{page_num:04d}.json",
                bundle_page,
            )
            artifacts.append(
                BuildArtifact(
                    path=f"pages/p{page_num:04d}.json",
                    artifact_type="bundle_page",
                    size_bytes=path.stat().st_size,
                )
            )

        # Copy image assets from extract stage to bundle
        asset_entries: list[BundleAssetEntry] = []
        extract_assets_dir = (
            ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "extract_primitives")
            / "assets"
            / "raw"
        )
        if extract_assets_dir.is_dir():
            bundle_assets_dir = (
                ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, STAGE_NAME)
                / "site_bundle"
                / ctx.doc_id
                / "assets"
            )
            bundle_assets_dir.mkdir(parents=True, exist_ok=True)
            for asset_file in sorted(extract_assets_dir.iterdir()):
                if asset_file.is_file() and asset_file.suffix in (
                    ".png",
                    ".jpeg",
                    ".jpg",
                    ".gif",
                    ".svg",
                    ".webp",
                ):
                    dest = bundle_assets_dir / asset_file.name
                    shutil.copy2(asset_file, dest)
                    content_type = f"image/{asset_file.suffix.lstrip('.')}".replace("jpg", "jpeg")
                    asset_entries.append(
                        BundleAssetEntry(
                            asset_ref=asset_file.name,
                            path=f"assets/{asset_file.name}",
                            content_type=content_type,
                            size_bytes=dest.stat().st_size,
                        )
                    )
                    artifacts.append(
                        BuildArtifact(
                            path=f"assets/{asset_file.name}",
                            artifact_type="image_asset",
                            size_bytes=dest.stat().st_size,
                        )
                    )
            ctx.logger.info("assets_copied", count=len(asset_entries), dest=str(bundle_assets_dir))

        # Copy navigation
        has_navigation = False
        try:
            nav = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "enrich_content",
                "navigation.json",
                NavigationTree,
            )
            nav_path = ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"site_bundle/{ctx.doc_id}/navigation.json",
                nav,
            )
            has_navigation = nav.total_entries > 0
            artifacts.append(
                BuildArtifact(
                    path="navigation.json",
                    artifact_type="navigation",
                    size_bytes=nav_path.stat().st_size,
                )
            )
        except FileNotFoundError:
            ctx.logger.warning("navigation_not_found_for_export")

        # Copy search documents
        has_search = False
        try:
            search = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "enrich_content",
                "search_documents.json",
                SearchIndex,
            )
            search_path = ctx.artifact_store.write_artifact(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                f"site_bundle/{ctx.doc_id}/search_documents.json",
                search,
            )
            has_search = search.total_documents > 0
            artifacts.append(
                BuildArtifact(
                    path="search_documents.json",
                    artifact_type="search_index",
                    size_bytes=search_path.stat().st_size,
                )
            )
        except FileNotFoundError:
            ctx.logger.warning("search_documents_not_found_for_export")

        # Read doc summary
        doc_summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "doc_summary.json",
            DocumentSummary,
        )

        # Read QA summary
        qa_accepted = True
        try:
            qa_summary = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "evaluate_qa",
                "summary.json",
                QASummary,
            )
            qa_accepted = qa_summary.accepted
        except FileNotFoundError:
            ctx.logger.warning("qa_summary_not_found_for_export")

        # Write bundle manifest
        bundle_manifest = SiteBundleManifest(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            page_count=manifest.page_count,
            title_en=doc_summary.title_en,
            title_ru=doc_summary.title_ru,
            route_base=ctx.document_config.build.route_base,
            source_locale=ctx.document_config.source_locale,
            target_locale=ctx.document_config.target_locale,
            translation_coverage=doc_summary.translation_coverage,
            has_navigation=has_navigation,
            has_search=has_search,
            has_glossary=_export_glossary(ctx, artifacts),
            assets=asset_entries,
            qa_accepted=qa_accepted,
            stage_version=STAGE_VERSION,
        )
        manifest_path = ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            f"site_bundle/{ctx.doc_id}/bundle_manifest.json",
            bundle_manifest,
        )
        artifacts.append(
            BuildArtifact(
                path="bundle_manifest.json",
                artifact_type="bundle_manifest",
                size_bytes=manifest_path.stat().st_size,
            )
        )

        # Write build artifacts inventory
        build_artifacts = BuildArtifacts(
            doc_id=ctx.doc_id,
            run_id=ctx.run_id,
            artifacts=artifacts,
            total_artifacts=len(artifacts),
        )
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "build_artifacts.json",
            build_artifacts,
        )

        ctx.logger.info(
            "export_complete",
            pages=manifest.page_count,
            artifacts=len(artifacts),
            qa_accepted=qa_accepted,
        )
