"""Tests for the resolve_assets_symbols stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.models.config_models import (
    DocumentBuild,
    DocumentConfig,
    DocumentProfiles,
    DocumentTitles,
    GlossaryPack,
    ModelProfile,
    RuleProfile,
    SymbolDetectionConfig,
    SymbolEntry,
    SymbolPack,
)
from aeon_reader_pipeline.models.ir_models import (
    CaptionBlock,
    FigureBlock,
    PageRecord,
    SymbolRef,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    AssetManifest,
    ResolveAssetsSymbolsStage,
)


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
    symbol_pack: SymbolPack | None = None,
) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id=run_id),
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test", ru="Тест"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="rulebook-default",
                models="translate-default",
                symbols="aeon-core",
                glossary="aeon-core",
            ),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(profile_id="test", provider="gemini", model="gemini-2.0-flash"),
        symbol_pack=symbol_pack or SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _run_through_resolve(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)


def _create_figure_caption_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Content Title", fontsize=18, fontname="hebo")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0)
    pix.set_rect(pix.irect, (100, 100, 200))
    page.insert_image(pymupdf.Rect(72, 100, 200, 200), pixmap=pix)
    page.insert_text((72, 220), "Figure 1: Test diagram", fontsize=10, fontname="heit")
    page.insert_text((72, 260), "After the figure.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _create_symbol_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Use the SWORD to attack.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


class TestResolveAssetsSymbols:
    def test_figure_caption_linked(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_figure_caption_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_resolve(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "pages/p0001.json",
            PageRecord,
        )
        figures = [b for b in record.blocks if isinstance(b, FigureBlock)]
        captions = [b for b in record.blocks if isinstance(b, CaptionBlock)]

        assert len(figures) >= 1
        fig = figures[0]
        assert fig.caption_block_id is not None

        # Caption should reference the figure
        if captions:
            cap = captions[0]
            assert cap.parent_block_id == fig.block_id

    def test_asset_manifest_created(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_figure_caption_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_resolve(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "assets.json",
            AssetManifest,
        )
        assert manifest.doc_id == "test-doc"
        assert len(manifest.assets) >= 1
        asset = manifest.assets[0]
        assert asset.page_number == 1
        assert asset.source_file != ""

    def test_symbol_resolution(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_symbol_pdf(pdf)

        pack = SymbolPack(
            pack_id="test",
            version="1.0.0",
            symbols=[
                SymbolEntry(
                    symbol_id="sword",
                    label_en="Sword",
                    label_ru="Меч",
                    detection=SymbolDetectionConfig(text_tokens=["SWORD"]),
                ),
            ],
        )
        ctx = _make_context(tmp_path, pdf, symbol_pack=pack)
        _run_through_resolve(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "pages/p0001.json",
            PageRecord,
        )
        # Find symbol refs in content
        found_symbol = False
        for block in record.blocks:
            if hasattr(block, "content"):
                for node in block.content:
                    if isinstance(node, SymbolRef) and node.symbol_id == "sword":
                        found_symbol = True
        assert found_symbol, "SWORD token should be resolved to a SymbolRef"

    def test_no_symbols_passthrough(self, tmp_path: Path) -> None:
        """With empty symbol pack, text passes through unchanged."""
        pdf = tmp_path / "source.pdf"
        _create_symbol_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_resolve(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "resolve_assets_symbols",
            "pages/p0001.json",
            PageRecord,
        )
        # Should have blocks but no SymbolRefs
        for block in record.blocks:
            if hasattr(block, "content"):
                for node in block.content:
                    assert not isinstance(node, SymbolRef)

    def test_stage_registration(self) -> None:
        stage = ResolveAssetsSymbolsStage()
        assert stage.name == "resolve_assets_symbols"
        assert stage.version == "1.0.0"
