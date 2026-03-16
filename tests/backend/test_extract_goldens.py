"""Golden tests for extraction stage — catches regressions in extraction output."""

from __future__ import annotations

import json
from pathlib import Path

import orjson
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
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
PDF_FIXTURES_DIR = FIXTURES_DIR / "pdf"
GOLDENS_DIR = Path(__file__).parent / "goldens" / "extract"

# Set to True to regenerate golden files (run once, then set back to False)
_REGENERATE = False


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "fixture",
    run_id: str = "golden-run",
) -> StageContext:
    """Build a StageContext for golden tests."""
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
            slug=doc_id,
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Fixture", ru="Фикстура"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base=f"/docs/{doc_id}"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(profile_id="test", provider="gemini", model="gemini-2.0-flash"),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _run_extraction(ctx: StageContext) -> list[ExtractedPage]:
    """Run ingest + extract, return all extracted pages."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)

    manifest = ctx.artifact_store.read_artifact(
        ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
    )
    pages: list[ExtractedPage] = []
    for i in range(1, manifest.page_count + 1):
        page = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "extract_primitives",
            f"pages/p{i:04d}.json",
            ExtractedPage,
        )
        pages.append(page)
    return pages


def _golden_path(fixture_name: str, page_number: int) -> Path:
    return GOLDENS_DIR / fixture_name / f"p{page_number:04d}.json"


def _serialize_for_golden(page: ExtractedPage) -> dict:
    """Serialize an ExtractedPage to a comparable dict.

    Strips fields that vary between runs (source_pdf_sha256, doc_id)
    and keeps the structural content stable.
    """
    data = json.loads(orjson.dumps(page.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS))
    # Remove run-specific fields to make golden comparison stable
    data.pop("source_pdf_sha256", None)
    data.pop("doc_id", None)
    return data


def _save_golden(fixture_name: str, page_number: int, page: ExtractedPage) -> None:
    """Save a golden file."""
    path = _golden_path(fixture_name, page_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialize_for_golden(page)
    path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))


def _load_golden(fixture_name: str, page_number: int) -> dict | None:
    """Load a golden file, or None if it doesn't exist."""
    path = _golden_path(fixture_name, page_number)
    if not path.exists():
        return None
    return json.loads(path.read_bytes())


def _compare_golden(fixture_name: str, page_number: int, page: ExtractedPage) -> None:
    """Compare extracted page against golden, or generate if missing."""
    actual = _serialize_for_golden(page)
    golden = _load_golden(fixture_name, page_number)

    if golden is None or _REGENERATE:
        _save_golden(fixture_name, page_number, page)
        if golden is None:
            pytest.skip(f"Golden generated for {fixture_name}/p{page_number:04d} — rerun")
        golden = actual  # Accept regenerated

    # Compare structural properties
    assert actual["page_number"] == golden["page_number"]
    assert actual["width_pt"] == pytest.approx(golden["width_pt"], abs=0.1)
    assert actual["height_pt"] == pytest.approx(golden["height_pt"], abs=0.1)
    assert actual["rotation"] == golden["rotation"]
    assert actual["char_count"] == golden["char_count"]
    assert actual["fonts_used"] == golden["fonts_used"]
    assert len(actual["text_blocks"]) == len(golden["text_blocks"])
    assert len(actual["images"]) == golden.get("images", []).__len__()

    # Deep compare text block content
    for actual_block, golden_block in zip(
        actual["text_blocks"], golden["text_blocks"], strict=True
    ):
        assert actual_block["block_type"] == golden_block["block_type"]
        assert len(actual_block["lines"]) == len(golden_block["lines"])
        for actual_line, golden_line in zip(
            actual_block["lines"], golden_block["lines"], strict=True
        ):
            actual_text = "".join(s["text"] for s in actual_line["spans"])
            golden_text = "".join(s["text"] for s in golden_line["spans"])
            assert actual_text == golden_text


class TestSimpleTextGoldens:
    """Golden tests for simple_text.pdf fixture."""

    FIXTURE = "simple_text"

    def test_page_1(self, tmp_path: Path) -> None:
        pdf = PDF_FIXTURES_DIR / f"{self.FIXTURE}.pdf"
        assert pdf.exists(), f"Fixture PDF missing: {pdf}"
        ctx = _make_context(tmp_path, pdf)
        pages = _run_extraction(ctx)
        assert len(pages) == 2
        _compare_golden(self.FIXTURE, 1, pages[0])

    def test_page_2(self, tmp_path: Path) -> None:
        pdf = PDF_FIXTURES_DIR / f"{self.FIXTURE}.pdf"
        ctx = _make_context(tmp_path, pdf)
        pages = _run_extraction(ctx)
        _compare_golden(self.FIXTURE, 2, pages[1])


class TestMultiformatGoldens:
    """Golden tests for multiformat.pdf fixture."""

    FIXTURE = "multiformat"

    def test_page_1(self, tmp_path: Path) -> None:
        pdf = PDF_FIXTURES_DIR / f"{self.FIXTURE}.pdf"
        assert pdf.exists(), f"Fixture PDF missing: {pdf}"
        ctx = _make_context(tmp_path, pdf)
        pages = _run_extraction(ctx)
        assert len(pages) == 1
        _compare_golden(self.FIXTURE, 1, pages[0])


class TestImagesGoldens:
    """Golden tests for with_images.pdf fixture."""

    FIXTURE = "with_images"

    def test_page_1(self, tmp_path: Path) -> None:
        pdf = PDF_FIXTURES_DIR / f"{self.FIXTURE}.pdf"
        assert pdf.exists(), f"Fixture PDF missing: {pdf}"
        ctx = _make_context(tmp_path, pdf)
        pages = _run_extraction(ctx)
        assert len(pages) == 1
        _compare_golden(self.FIXTURE, 1, pages[0])

    def test_images_extracted(self, tmp_path: Path) -> None:
        """The images fixture should detect embedded images."""
        pdf = PDF_FIXTURES_DIR / f"{self.FIXTURE}.pdf"
        ctx = _make_context(tmp_path, pdf)
        pages = _run_extraction(ctx)
        assert len(pages[0].images) == 2
        # Verify images have distinct hashes
        hashes = {img.content_hash for img in pages[0].images}
        assert len(hashes) == 2


class TestIngestGoldens:
    """Golden tests for DocumentManifest from ingest stage."""

    def test_simple_text_manifest(self, tmp_path: Path) -> None:
        """Simple text PDF produces stable manifest."""
        pdf = PDF_FIXTURES_DIR / "simple_text.pdf"
        assert pdf.exists()
        ctx = _make_context(tmp_path, pdf)
        IngestSourceStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert manifest.page_count == 2
        assert len(manifest.page_dimensions) == 2
        assert len(manifest.outline) == 2
        assert manifest.metadata.title == "Simple Text Fixture"

    def test_images_manifest(self, tmp_path: Path) -> None:
        """Images PDF produces correct page count and metadata."""
        pdf = PDF_FIXTURES_DIR / "with_images.pdf"
        assert pdf.exists()
        ctx = _make_context(tmp_path, pdf)
        IngestSourceStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert manifest.page_count == 1
        assert manifest.metadata.title == "Images Fixture"
