"""Tests for page-scoped preview runs (S5U-232).

Validates page range parsing, page filtering through pipeline stages,
and subset bundle export with correct manifest metadata.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from aeon_reader_pipeline.cli.main import app
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
from aeon_reader_pipeline.models.enrich_models import DocumentSummary
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.models.site_bundle_models import BundlePage, SiteBundleManifest
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.apply_safe_fixes import ApplySafeFixesStage
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.export_site_bundle import ExportSiteBundleStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    ResolveAssetsSymbolsStage,
)
from aeon_reader_pipeline.utils.page_filter import pages_to_process, parse_page_range

cli_runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _create_multi_page_pdf(path: Path) -> None:
    """Create a 3-page fixture PDF."""
    doc = pymupdf.open()
    for i in range(1, 4):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Chapter {i}", fontsize=20, fontname="hebo")
        page.insert_text((72, 120), f"Body text for page {i}.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_context(
    tmp_path: Path, pdf_path: Path, page_filter: list[int] | None = None
) -> StageContext:
    configs_root = tmp_path / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = tmp_path / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-pg", ["test-doc"])

    return StageContext(
        run_id="run-pg",
        doc_id="test-doc",
        pipeline_config=PipelineConfig(
            run_id="run-pg",
            source_only=True,
            skip_qa_gate=True,
            page_filter=page_filter,
        ),
        document_config=DocumentConfig(
            doc_id="test-doc",
            slug="test-doc",
            source_pdf=str(pdf_path),
            titles=DocumentTitles(en="Test Doc", ru="\u0422\u0435\u0441\u0442"),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(
            profile_id="test",
            provider="gemini",
            model="gemini-2.0-flash",
            prompt_bundle="translate-v1",
        ),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _run_structural_stages(ctx: StageContext) -> None:
    """Run stages 00-05 (structural, no translation)."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)


# ---------------------------------------------------------------------------
# parse_page_range tests
# ---------------------------------------------------------------------------


class TestParsePageRange:
    def test_single_page(self) -> None:
        assert parse_page_range("15") == [15]

    def test_range(self) -> None:
        assert parse_page_range("10-15") == [10, 11, 12, 13, 14, 15]

    def test_comma_separated(self) -> None:
        assert parse_page_range("1,5,8") == [1, 5, 8]

    def test_mixed(self) -> None:
        assert parse_page_range("1,5,8-12") == [1, 5, 8, 9, 10, 11, 12]

    def test_deduplication(self) -> None:
        assert parse_page_range("1,1,2-3,3") == [1, 2, 3]

    def test_sorted_output(self) -> None:
        assert parse_page_range("5,1,3") == [1, 3, 5]

    def test_invalid_page_zero(self) -> None:
        with pytest.raises(ValueError, match="Invalid page number"):
            parse_page_range("0")

    def test_invalid_range_reversed(self) -> None:
        with pytest.raises(ValueError, match="Invalid page range"):
            parse_page_range("15-10")

    def test_empty_spec(self) -> None:
        with pytest.raises(ValueError, match="Empty page specification"):
            parse_page_range("")


# ---------------------------------------------------------------------------
# pages_to_process tests
# ---------------------------------------------------------------------------


class TestPagesToProcess:
    def test_no_filter_returns_all(self) -> None:
        assert pages_to_process(5, None) == [1, 2, 3, 4, 5]

    def test_filter_within_range(self) -> None:
        assert pages_to_process(10, [2, 5, 8]) == [2, 5, 8]

    def test_filter_clamps_to_range(self) -> None:
        assert pages_to_process(3, [1, 2, 5, 10]) == [1, 2]

    def test_filter_all_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="No valid pages"):
            pages_to_process(3, [10, 20])


# ---------------------------------------------------------------------------
# PipelineConfig model tests
# ---------------------------------------------------------------------------


class TestPageFilterConfig:
    def test_default_none(self) -> None:
        config = PipelineConfig(run_id="test")
        assert config.page_filter is None

    def test_set_filter(self) -> None:
        config = PipelineConfig(run_id="test", page_filter=[1, 5, 10])
        assert config.page_filter == [1, 5, 10]


# ---------------------------------------------------------------------------
# Integration: page-scoped preview through full pipeline
# ---------------------------------------------------------------------------


class TestPageScopedPipeline:
    def test_single_page_preview(self, tmp_path: Path) -> None:
        """Run page 2 only through the source-only preview pipeline."""
        pdf = tmp_path / "source.pdf"
        _create_multi_page_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, page_filter=[2])

        # Structural stages
        _run_structural_stages(ctx)

        # Enrich (source-only, page 2 only)
        EnrichContentStage().execute(ctx)

        # QA (gate skipped)
        EvaluateQAStage().execute(ctx)

        # Apply fixes
        ApplySafeFixesStage().execute(ctx)

        # Export
        ExportSiteBundleStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.page_count == 1
        assert manifest.is_preview is True
        assert manifest.filtered_pages == [2]
        assert manifest.total_source_pages == 3

        # Verify only page 2 was exported
        page = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/pages/p0002.json",
            BundlePage,
        )
        assert page.page_number == 2

        # Verify page 1 was NOT exported
        with pytest.raises(FileNotFoundError):
            ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "export_site_bundle",
                "site_bundle/test-doc/pages/p0001.json",
                BundlePage,
            )

    def test_multi_page_subset(self, tmp_path: Path) -> None:
        """Run pages 1 and 3 only."""
        pdf = tmp_path / "source.pdf"
        _create_multi_page_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, page_filter=[1, 3])

        _run_structural_stages(ctx)
        EnrichContentStage().execute(ctx)
        EvaluateQAStage().execute(ctx)
        ApplySafeFixesStage().execute(ctx)
        ExportSiteBundleStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.page_count == 2
        assert manifest.is_preview is True
        assert manifest.filtered_pages == [1, 3]
        assert manifest.total_source_pages == 3

    def test_no_filter_produces_full_bundle(self, tmp_path: Path) -> None:
        """Without page filter, all pages are exported and bundle is not preview."""
        pdf = tmp_path / "source.pdf"
        _create_multi_page_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, page_filter=None)

        _run_structural_stages(ctx)
        EnrichContentStage().execute(ctx)
        EvaluateQAStage().execute(ctx)
        ApplySafeFixesStage().execute(ctx)
        ExportSiteBundleStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.page_count == 3
        assert manifest.is_preview is False
        assert manifest.filtered_pages is None
        assert manifest.total_source_pages is None

    def test_doc_summary_reflects_filtered_pages(self, tmp_path: Path) -> None:
        """The doc summary should reflect only the filtered pages."""
        pdf = tmp_path / "source.pdf"
        _create_multi_page_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, page_filter=[2])

        _run_structural_stages(ctx)
        EnrichContentStage().execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "doc_summary.json",
            DocumentSummary,
        )
        assert summary.page_count == 1


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestPagesCLI:
    def test_help_shows_pages_option(self) -> None:
        result = cli_runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--pages" in output
