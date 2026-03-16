"""Tests for the ingest_source stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from aeon_reader_pipeline.config.hashing import hash_file
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
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage


def _create_fixture_pdf(path: Path, *, pages: int = 3, with_toc: bool = True) -> None:
    """Create a minimal fixture PDF with text and optional TOC."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {i + 1} heading", fontsize=16)
        page.insert_text((72, 120), f"Body text on page {i + 1}.", fontsize=11)
    if with_toc:
        toc = [[1, "Chapter 1", 1], [2, "Section 1.1", 2], [1, "Chapter 2", 3]]
        doc.set_toc(toc)
    doc.set_metadata({"title": "Test Document", "author": "Fixture Generator"})
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
    # configs_root is set so that configs_root.parent / source_pdf resolves correctly
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


class TestIngestSource:
    """Tests for IngestSourceStage."""

    def test_produces_manifest(self, tmp_path: Path) -> None:
        """Ingesting a fixture PDF produces a valid DocumentManifest."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path)
        ctx = _make_context(tmp_path, pdf_path)
        stage = IngestSourceStage()

        stage.execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert manifest.doc_id == "test-doc"
        assert manifest.page_count == 3
        assert manifest.source_pdf_sha256 == hash_file(str(pdf_path))
        assert manifest.file_size_bytes == pdf_path.stat().st_size

    def test_page_dimensions(self, tmp_path: Path) -> None:
        """Page dimensions match the fixture PDF."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path)
        ctx = _make_context(tmp_path, pdf_path)
        IngestSourceStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert len(manifest.page_dimensions) == 3
        dim = manifest.page_dimensions[0]
        assert dim.page_number == 1
        assert dim.width_pt == pytest.approx(612.0, abs=1)
        assert dim.height_pt == pytest.approx(792.0, abs=1)

    def test_outline_extraction(self, tmp_path: Path) -> None:
        """TOC entries are extracted."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path, with_toc=True)
        ctx = _make_context(tmp_path, pdf_path)
        IngestSourceStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert len(manifest.outline) == 3
        assert manifest.outline[0].title == "Chapter 1"
        assert manifest.outline[0].level == 1
        assert manifest.outline[1].level == 2

    def test_metadata_extraction(self, tmp_path: Path) -> None:
        """PDF metadata is captured."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path)
        ctx = _make_context(tmp_path, pdf_path)
        IngestSourceStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert manifest.metadata.title == "Test Document"
        assert manifest.metadata.author == "Fixture Generator"

    def test_reproducible_hash(self, tmp_path: Path) -> None:
        """Running ingest twice on the same PDF produces the same hash."""
        pdf_path = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf_path)

        ctx1 = _make_context(tmp_path / "run1", pdf_path, run_id="run-a")
        ctx2 = _make_context(tmp_path / "run2", pdf_path, run_id="run-b")

        IngestSourceStage().execute(ctx1)
        IngestSourceStage().execute(ctx2)

        m1 = ctx1.artifact_store.read_artifact(
            "run-a", "test-doc", "ingest_source", "document_manifest.json", DocumentManifest
        )
        m2 = ctx2.artifact_store.read_artifact(
            "run-b", "test-doc", "ingest_source", "document_manifest.json", DocumentManifest
        )
        assert m1.source_pdf_sha256 == m2.source_pdf_sha256
        assert m1.page_count == m2.page_count

    def test_missing_pdf_raises(self, tmp_path: Path) -> None:
        """Missing source PDF raises FileNotFoundError."""
        missing = tmp_path / "does_not_exist.pdf"
        ctx = _make_context(tmp_path, missing)
        with pytest.raises(FileNotFoundError, match="Source PDF not found"):
            IngestSourceStage().execute(ctx)

    def test_stage_registration(self) -> None:
        """Stage is registered with correct name and version."""
        stage = IngestSourceStage()
        assert stage.name == "ingest_source"
        assert stage.version == "1.0.0"
