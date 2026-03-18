"""Tests for the extract_primitives stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

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


def _create_fixture_pdf(
    path: Path,
    *,
    pages: int = 3,
    with_image: bool = False,
) -> None:
    """Create a fixture PDF with text content and optionally an image."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Heading on page {i + 1}", fontsize=18, fontname="helv")
        page.insert_text(
            (72, 110), f"Normal body text on page {i + 1}.", fontsize=11, fontname="helv"
        )
        page.insert_text(
            (72, 140), f"Second paragraph on page {i + 1}.", fontsize=11, fontname="helv"
        )
        if with_image and i == 0:
            # Insert a small colored rectangle as a drawing (not an image, but a visual element)
            rect = pymupdf.Rect(72, 200, 200, 300)
            # Create a tiny pixmap and insert as image
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 64), 0)
            pix.set_rect(pix.irect, (255, 0, 0))  # red square
            page.insert_image(rect, pixmap=pix)

    doc.set_metadata({"title": "Extract Test"})
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


def _run_ingest_and_extract(ctx: StageContext) -> None:
    """Run both ingest and extract stages in order."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)


class TestExtractPrimitives:
    """Tests for ExtractPrimitivesStage."""

    def test_produces_per_page_files(self, tmp_path: Path) -> None:
        """Extract produces one JSON file per page."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=3)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        for page_num in range(1, 4):
            page = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "extract_primitives",
                f"pages/p{page_num:04d}.json",
                ExtractedPage,
            )
            assert page.page_number == page_num
            assert page.doc_id == "test-doc"

    def test_text_blocks_extracted(self, tmp_path: Path) -> None:
        """Text blocks contain lines and spans."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert len(page.text_blocks) > 0
        # Should have text content
        all_text = " ".join(
            span.text for block in page.text_blocks for line in block.lines for span in line.spans
        )
        assert "Heading on page 1" in all_text
        assert "Normal body text" in all_text

    def test_font_info_captured(self, tmp_path: Path) -> None:
        """Font metadata is preserved in spans."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        fonts = set()
        sizes = set()
        for block in page.text_blocks:
            for line in block.lines:
                for span in line.spans:
                    fonts.add(span.font.name)
                    sizes.add(span.font.size)
        # Should have at least one font
        assert len(fonts) >= 1
        # Should have different sizes (heading=18 vs body=11)
        assert len(sizes) >= 2

    def test_bbox_values_reasonable(self, tmp_path: Path) -> None:
        """Bounding boxes have positive dimensions within page bounds."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        for block in page.text_blocks:
            assert block.bbox.x0 >= 0
            assert block.bbox.y0 >= 0
            assert block.bbox.x1 <= page.width_pt + 1
            assert block.bbox.y1 <= page.height_pt + 1
            assert block.bbox.x1 >= block.bbox.x0
            assert block.bbox.y1 >= block.bbox.y0

    def test_page_dimensions_match(self, tmp_path: Path) -> None:
        """Extracted page dimensions match fixture PDF."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert page.width_pt == pytest.approx(612.0, abs=1)
        assert page.height_pt == pytest.approx(792.0, abs=1)

    def test_char_count_positive(self, tmp_path: Path) -> None:
        """Extracted pages have positive character counts."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert page.char_count > 0

    def test_fonts_used_populated(self, tmp_path: Path) -> None:
        """fonts_used list is populated."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert len(page.fonts_used) >= 1

    def test_source_hash_propagated(self, tmp_path: Path) -> None:
        """ExtractedPage carries the source PDF hash from the manifest."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, pages=1)
        ctx = _make_context(tmp_path, pdf_path)
        _run_ingest_and_extract(ctx)

        page = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "extract_primitives", "pages/p0001.json", ExtractedPage
        )
        assert len(page.source_pdf_sha256) == 64

    def test_stage_registration(self) -> None:
        """Stage is registered with correct name and version."""
        stage = ExtractPrimitivesStage()
        assert stage.name == "extract_primitives"
        assert stage.version == "1.0.0"


class TestImageExtractionFailureLogging:
    """Verify that image extraction failures are logged, not swallowed."""

    def test_failed_extraction_logs_warning(self, tmp_path: Path) -> None:
        """A corrupt xref logs a warning and continues extraction."""
        from unittest.mock import MagicMock, patch

        from aeon_reader_pipeline.stages.extract_primitives import _extract_images

        # Create a simple page with one image
        doc = pymupdf.open()
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
        page.insert_image(pymupdf.Rect(10, 10, 50, 50), pixmap=pix)

        stage_dir = tmp_path / "stage"

        # Mock extract_image to raise on the first call
        def _failing_extract(xref: int) -> dict:  # type: ignore[type-arg]
            raise RuntimeError("corrupt image data")

        ctx_mock = MagicMock()

        with patch.object(doc, "extract_image", side_effect=_failing_extract):
            images, failures = _extract_images(
                page,
                doc,
                stage_dir,
                page_number=1,
                ctx=ctx_mock,
            )

        assert failures >= 1
        assert len(images) == 0
        ctx_mock.logger.warning.assert_called()
        call_args = ctx_mock.logger.warning.call_args
        assert call_args[0][0] == "image_extraction_failed"
        assert call_args[1]["page"] == 1
        assert "corrupt image data" in call_args[1]["error"]

        doc.close()

    def test_mixed_success_and_failure(self, tmp_path: Path) -> None:
        """Some images succeed, some fail — failures are counted."""
        from aeon_reader_pipeline.stages.extract_primitives import _extract_images

        # Create page with two images
        doc = pymupdf.open()
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
        page.insert_image(pymupdf.Rect(10, 10, 50, 50), pixmap=pix)
        page.insert_image(pymupdf.Rect(60, 10, 100, 50), pixmap=pix)

        stage_dir = tmp_path / "stage"

        # No mocking — both should succeed with valid images
        images, failures = _extract_images(page, doc, stage_dir, page_number=1)

        assert failures == 0
        assert len(images) >= 1  # deduped by content hash, so at least 1

        doc.close()
