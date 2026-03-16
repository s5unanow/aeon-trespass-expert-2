"""Tests for site bundle public contract models."""

from __future__ import annotations

from aeon_reader_pipeline.models.site_bundle_models import (
    BuildArtifact,
    BuildArtifacts,
    BundleCalloutBlock,
    BundleDividerBlock,
    BundleFigureBlock,
    BundleHeadingBlock,
    BundleListBlock,
    BundleListItemBlock,
    BundlePage,
    BundlePageAnchor,
    BundleParagraphBlock,
    BundleTableBlock,
    BundleTextRun,
    CatalogEntry,
    CatalogManifest,
    SiteBundleManifest,
)


class TestBundlePage:
    def test_minimal_page(self) -> None:
        page = BundlePage(
            page_number=1,
            doc_id="doc-1",
            width_pt=612,
            height_pt=792,
        )
        assert page.render_mode == "semantic"
        assert page.blocks == []
        assert page.anchors == []

    def test_page_with_blocks(self) -> None:
        page = BundlePage(
            page_number=1,
            doc_id="doc-1",
            width_pt=612,
            height_pt=792,
            blocks=[
                BundleHeadingBlock(block_id="h1", level=1, content=[BundleTextRun(text="Title")]),
                BundleParagraphBlock(block_id="p1", content=[BundleTextRun(text="Body", ru_text="[RU]")]),
            ],
        )
        assert len(page.blocks) == 2

    def test_no_internal_fields(self) -> None:
        """BundlePage should not have source_pdf_sha256 or fingerprint."""
        page = BundlePage(page_number=1, doc_id="d", width_pt=1, height_pt=1)
        data = page.model_dump()
        assert "source_pdf_sha256" not in data
        assert "fingerprint" not in data

    def test_text_run_no_font_fields(self) -> None:
        """BundleTextRun should not have font_name or font_size."""
        run = BundleTextRun(text="hello")
        data = run.model_dump()
        assert "font_name" not in data
        assert "font_size" not in data

    def test_heading_no_source_block_index(self) -> None:
        block = BundleHeadingBlock(block_id="h1")
        data = block.model_dump()
        assert "source_block_index" not in data

    def test_all_block_types(self) -> None:
        page = BundlePage(
            page_number=1,
            doc_id="d",
            width_pt=1,
            height_pt=1,
            blocks=[
                BundleHeadingBlock(block_id="h1"),
                BundleParagraphBlock(block_id="p1"),
                BundleListBlock(
                    block_id="l1",
                    items=[BundleListItemBlock(block_id="li1", bullet="-")],
                ),
                BundleFigureBlock(block_id="f1", asset_ref="img.png"),
                BundleTableBlock(block_id="t1", rows=2, cols=3),
                BundleCalloutBlock(block_id="c1", callout_type="tip"),
                BundleDividerBlock(block_id="d1"),
            ],
            anchors=[BundlePageAnchor(anchor_id="a1", block_id="h1")],
        )
        assert len(page.blocks) == 7
        assert len(page.anchors) == 1


class TestSiteBundleManifest:
    def test_defaults(self) -> None:
        m = SiteBundleManifest(doc_id="d", run_id="r", page_count=5, title_en="T")
        assert m.qa_accepted is True
        assert m.has_navigation is False
        assert m.translation_coverage == 0.0

    def test_roundtrip(self) -> None:
        m = SiteBundleManifest(
            doc_id="d",
            run_id="r",
            page_count=3,
            title_en="EN",
            title_ru="RU",
            route_base="/docs/d",
            translation_coverage=0.95,
            has_navigation=True,
            has_search=True,
        )
        data = m.model_dump()
        restored = SiteBundleManifest.model_validate(data)
        assert restored.doc_id == "d"
        assert restored.translation_coverage == 0.95


class TestCatalogManifest:
    def test_empty_catalog(self) -> None:
        c = CatalogManifest()
        assert c.total_documents == 0

    def test_with_entries(self) -> None:
        c = CatalogManifest(
            documents=[
                CatalogEntry(doc_id="d1", slug="d1", title_en="Doc 1", page_count=10),
                CatalogEntry(doc_id="d2", slug="d2", title_en="Doc 2", page_count=5),
            ],
            total_documents=2,
        )
        assert len(c.documents) == 2


class TestBuildArtifacts:
    def test_inventory(self) -> None:
        ba = BuildArtifacts(
            doc_id="d",
            run_id="r",
            artifacts=[
                BuildArtifact(path="pages/p0001.json", artifact_type="bundle_page"),
            ],
            total_artifacts=1,
        )
        assert ba.total_artifacts == 1
