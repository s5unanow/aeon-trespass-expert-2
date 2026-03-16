"""Tests for the patch/override layer and hybrid fallback."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from aeon_reader_pipeline.config.patch_applier import apply_patches
from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.models.config_models import (
    DocumentBuild,
    DocumentConfig,
    DocumentProfiles,
    DocumentTitles,
    GlossaryPack,
    ModelProfile,
    PatchEntry,
    PatchSet,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.ir_models import (
    HeadingBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
    patch_set: PatchSet | None = None,
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
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=patch_set,
        artifact_store=store,
        configs_root=configs_root,
    )


def _create_simple_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Title Text", fontsize=18, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


class TestPatchApplierUnit:
    """Unit tests for apply_patches function."""

    def test_no_patches_passthrough(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[ParagraphBlock(block_id="p1", content=[TextRun(text="Hello")])],
        )
        result = apply_patches(record, None)
        assert result == record

    def test_empty_patches_passthrough(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[ParagraphBlock(block_id="p1", content=[TextRun(text="Hello")])],
        )
        ps = PatchSet(doc_id="doc", version="1.0", patches=[])
        result = apply_patches(record, ps)
        assert len(result.blocks) == 1

    def test_override_block_kind(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[ParagraphBlock(block_id="p1", content=[TextRun(text="Should be heading")])],
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="fix-1",
                    target_page=1,
                    target_block_id="p1",
                    action="override_block_kind",
                    payload={"new_kind": "heading"},
                    reason="Misclassified paragraph",
                )
            ],
        )
        result = apply_patches(record, ps)
        assert isinstance(result.blocks[0], HeadingBlock)
        assert result.blocks[0].block_id == "p1"

    def test_set_render_mode(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="hybrid-1",
                    target_page=1,
                    action="set_render_mode",
                    payload={"render_mode": "hybrid"},
                )
            ],
        )
        result = apply_patches(record, ps)
        assert result.render_mode == "hybrid"

    def test_force_fallback(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="fallback-1",
                    target_page=1,
                    action="force_fallback",
                )
            ],
        )
        result = apply_patches(record, ps)
        assert result.render_mode == "facsimile"

    def test_replace_text(self):
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[ParagraphBlock(block_id="p1", content=[TextRun(text="Old text")])],
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="fix-text-1",
                    target_page=1,
                    target_block_id="p1",
                    action="replace_text",
                    payload={"text": "Corrected text"},
                )
            ],
        )
        result = apply_patches(record, ps)
        content = result.blocks[0].content
        assert len(content) == 1
        assert content[0].text == "Corrected text"

    def test_page_filter(self):
        """Patches targeting a different page are not applied."""
        record = PageRecord(
            page_number=2,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="other-page",
                    target_page=1,
                    action="force_fallback",
                )
            ],
        )
        result = apply_patches(record, ps)
        assert result.render_mode == "semantic"  # unchanged

    def test_idempotent(self):
        """Applying the same patch twice produces the same result."""
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[ParagraphBlock(block_id="p1", content=[TextRun(text="Text")])],
        )
        ps = PatchSet(
            doc_id="doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="fix-1",
                    target_page=1,
                    target_block_id="p1",
                    action="override_block_kind",
                    payload={"new_kind": "heading"},
                )
            ],
        )
        r1 = apply_patches(record, ps)
        r2 = apply_patches(r1, ps)
        assert r1.blocks[0].kind == r2.blocks[0].kind == "heading"


class TestPatchesIntegration:
    """Integration tests: patches applied during normalize_layout."""

    def test_force_fallback_in_pipeline(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)

        ps = PatchSet(
            doc_id="test-doc",
            version="1.0",
            patches=[
                PatchEntry(
                    patch_id="fallback-p1",
                    target_page=1,
                    action="force_fallback",
                    reason="Page too complex for semantic rendering",
                )
            ],
        )
        ctx = _make_context(tmp_path, pdf, patch_set=ps)
        IngestSourceStage().execute(ctx)
        ExtractPrimitivesStage().execute(ctx)
        NormalizeLayoutStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "normalize_layout",
            "pages/p0001.json",
            PageRecord,
        )
        assert record.render_mode == "facsimile"

    def test_no_patches_stays_semantic(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        IngestSourceStage().execute(ctx)
        ExtractPrimitivesStage().execute(ctx)
        NormalizeLayoutStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "normalize_layout",
            "pages/p0001.json",
            PageRecord,
        )
        assert record.render_mode == "semantic"
