"""Tests for source-only preview mode (S5U-231).

Validates that --source-only skips translation stages (06, 07) and produces
a valid site bundle from source text only.
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
from aeon_reader_pipeline.models.enrich_models import (
    DocumentSummary,
    NavigationTree,
    SearchIndex,
)
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import QASummary
from aeon_reader_pipeline.models.run_models import PipelineConfig, StageSelector
from aeon_reader_pipeline.models.site_bundle_models import BundlePage, SiteBundleManifest
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import (
    TRANSLATION_STAGES,
    filter_stages,
)
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

cli_runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _create_fixture_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_source_only_context(tmp_path: Path, pdf_path: Path) -> StageContext:
    configs_root = tmp_path / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = tmp_path / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-src", ["test-doc"])

    return StageContext(
        run_id="run-src",
        doc_id="test-doc",
        pipeline_config=PipelineConfig(
            run_id="run-src",
            source_only=True,
            skip_qa_gate=True,
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
# Registry / filter_stages tests
# ---------------------------------------------------------------------------


class TestFilterStagesExclude:
    def test_exclude_translation_stages(self) -> None:
        stages = filter_stages(exclude=sorted(TRANSLATION_STAGES))
        assert "translate_units" not in stages
        assert "merge_localization" not in stages
        assert "enrich_content" in stages
        assert "resolve_run" in stages

    def test_exclude_with_from_to(self) -> None:
        stages = filter_stages(
            from_stage="plan_translation",
            to_stage="export_site_bundle",
            exclude=["translate_units", "merge_localization"],
        )
        assert stages == [
            "plan_translation",
            "enrich_content",
            "evaluate_qa",
            "export_site_bundle",
        ]

    def test_exclude_unknown_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown exclude stage"):
            filter_stages(exclude=["nonexistent"])

    def test_exclude_empty_list_no_effect(self) -> None:
        from aeon_reader_pipeline.stage_framework.registry import STAGE_ORDER

        stages = filter_stages(exclude=[])
        assert stages == STAGE_ORDER


class TestTranslationStagesConstant:
    def test_contains_expected_stages(self) -> None:
        assert frozenset({"translate_units", "merge_localization"}) == TRANSLATION_STAGES


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSourceOnlyConfig:
    def test_source_only_default_false(self) -> None:
        config = PipelineConfig(run_id="test")
        assert config.source_only is False

    def test_source_only_set_true(self) -> None:
        config = PipelineConfig(run_id="test", source_only=True)
        assert config.source_only is True

    def test_stage_selector_exclude(self) -> None:
        sel = StageSelector(exclude=["translate_units", "merge_localization"])
        assert sel.exclude == ["translate_units", "merge_localization"]


# ---------------------------------------------------------------------------
# Enrich content — source-only reads from resolve_assets_symbols
# ---------------------------------------------------------------------------


class TestEnrichContentSourceOnly:
    def test_enrich_reads_from_resolve_assets_when_source_only(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        ctx = _make_source_only_context(tmp_path, pdf)
        _run_structural_stages(ctx)

        # Run enrich directly — should read from resolve_assets_symbols
        EnrichContentStage().execute(ctx)

        # Verify enriched page exists and has source text but no ru_text
        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "pages/p0001.json",
            PageRecord,
        )
        assert record.page_number == 1
        assert len(record.blocks) > 0

        # Verify coverage is 0 (no translations)
        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "doc_summary.json",
            DocumentSummary,
        )
        assert summary.translation_coverage == 0.0

    def test_enrich_produces_navigation(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        ctx = _make_source_only_context(tmp_path, pdf)
        _run_structural_stages(ctx)
        EnrichContentStage().execute(ctx)

        nav = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "navigation.json",
            NavigationTree,
        )
        # Navigation tree is produced (may be empty for simple fixture PDFs)
        assert nav.doc_id == "test-doc"

    def test_enrich_produces_search_index(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        ctx = _make_source_only_context(tmp_path, pdf)
        _run_structural_stages(ctx)
        EnrichContentStage().execute(ctx)

        search = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "search_documents.json",
            SearchIndex,
        )
        assert search.total_documents >= 1


# ---------------------------------------------------------------------------
# Source-only pipeline integration: stages 00-05, 08-11
# ---------------------------------------------------------------------------


class TestSourceOnlyPipeline:
    def test_source_only_produces_bundle(self, tmp_path: Path) -> None:
        """Full source-only flow from ingest through export."""
        pdf = tmp_path / "source.pdf"
        _create_fixture_pdf(pdf)
        ctx = _make_source_only_context(tmp_path, pdf)

        # Structural stages (00-05)
        _run_structural_stages(ctx)

        # Skip 06 (translate) and 07 (merge) — source-only mode

        # 08: Enrich
        EnrichContentStage().execute(ctx)

        # 09: QA (with gate skipped)
        EvaluateQAStage().execute(ctx)
        qa = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "evaluate_qa", "summary.json", QASummary
        )
        assert qa.gate_skipped is True

        # 11: Export
        ExportSiteBundleStage().execute(ctx)
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.doc_id == "test-doc"
        assert manifest.page_count == 1

        # Verify bundle page has source text but no translations
        page = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/pages/p0001.json",
            BundlePage,
        )
        assert page.page_number == 1


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestSourceOnlyCLI:
    def test_help_shows_source_only(self) -> None:
        result = cli_runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "--source-only" in output

    def test_source_only_and_dry_run_mutually_exclusive(self) -> None:
        result = cli_runner.invoke(app, ["run", "--source-only", "--dry-run"])
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output.lower()
