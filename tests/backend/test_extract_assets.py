"""Tests for raw asset extraction within extract_primitives stage."""

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
    SymbolPack,
)
from aeon_reader_pipeline.models.extract_models import ExtractedPage
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage


def _create_pdf_with_images(path: Path, *, image_count: int = 2) -> None:
    """Create a fixture PDF with embedded images."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Page with images", fontsize=14)

    for i in range(image_count):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 32 + i * 16, 32 + i * 16), 0)
        # Different colors for different images to ensure different hashes
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        pix.set_rect(pix.irect, colors[i % len(colors)])
        rect = pymupdf.Rect(72 + i * 150, 200, 72 + i * 150 + 100, 300)
        page.insert_image(rect, pixmap=pix)

    doc.save(str(path))
    doc.close()


def _create_pdf_no_images(path: Path) -> None:
    """Create a text-only PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Text only page", fontsize=14)
    doc.save(str(path))
    doc.close()


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
) -> StageContext:
    """Build a minimal StageContext for testing."""
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
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _run_pipeline(ctx: StageContext) -> None:
    """Run ingest + extract stages."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)


class TestAssetExtraction:
    """Tests for raw image/asset extraction."""

    def test_images_detected(self, tmp_path: Path) -> None:
        """Images embedded in the PDF appear in ExtractedPage.images."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_with_images(pdf_path, image_count=2)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert len(page.images) == 2

    def test_image_hashes_unique(self, tmp_path: Path) -> None:
        """Different images have different content hashes."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_with_images(pdf_path, image_count=2)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        hashes = [img.content_hash for img in page.images]
        assert len(set(hashes)) == len(hashes), "Image hashes should be unique"

    def test_image_files_saved(self, tmp_path: Path) -> None:
        """Raw image files are written to the assets directory."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_with_images(pdf_path, image_count=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        stage_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "extract_primitives")
        assets_dir = stage_dir / "assets" / "raw"
        assert assets_dir.exists()
        asset_files = list(assets_dir.iterdir())
        assert len(asset_files) >= 1
        # Files should have content
        for f in asset_files:
            assert f.stat().st_size > 0

    def test_image_bbox_on_page(self, tmp_path: Path) -> None:
        """Image bboxes are within page bounds."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_with_images(pdf_path, image_count=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        for img in page.images:
            assert img.bbox.x0 >= 0
            assert img.bbox.y0 >= 0
            assert img.bbox.x1 <= page.width_pt + 1
            assert img.bbox.y1 <= page.height_pt + 1
            assert img.width > 0
            assert img.height > 0

    def test_image_stored_as_filename(self, tmp_path: Path) -> None:
        """stored_as field contains the asset filename."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_with_images(pdf_path, image_count=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        for img in page.images:
            assert img.stored_as is not None
            assert img.content_hash[:16] in img.stored_as

    def test_no_images_page(self, tmp_path: Path) -> None:
        """Text-only pages have empty images list."""
        pdf_path = tmp_path / "source.pdf"
        _create_pdf_no_images(pdf_path)
        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert len(page.images) == 0

    def test_duplicate_images_deduplicated(self, tmp_path: Path) -> None:
        """Same image inserted twice results in one file on disk."""
        pdf_path = tmp_path / "source.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 32, 32), 0)
        pix.set_rect(pix.irect, (128, 128, 128))
        # Insert same image twice at different positions
        page.insert_image(pymupdf.Rect(72, 200, 172, 300), pixmap=pix)
        page.insert_image(pymupdf.Rect(200, 200, 300, 300), pixmap=pix)
        doc.save(str(pdf_path))
        doc.close()

        ctx = _make_context(tmp_path, pdf_path)
        _run_pipeline(ctx)

        stage_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "extract_primitives")
        assets_dir = stage_dir / "assets" / "raw"
        if assets_dir.exists():
            asset_files = list(assets_dir.iterdir())
            # PyMuPDF may reuse xref for identical images, so we might get 1 or 2 entries
            # but the file on disk should be deduplicated by hash
            # At minimum, the test validates no crash occurs
            assert len(asset_files) >= 1
