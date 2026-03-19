"""Tests for QA quality gate logic."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
from aeon_reader_pipeline.models.config_models import (
    DocumentBuild,
    DocumentConfig,
    DocumentProfiles,
    DocumentTitles,
    GlossaryPack,
    ModelProfile,
    QAGateConfig,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.qa_models import QAIssue, QASummary
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.qa import QualityGateError
from aeon_reader_pipeline.qa.engine import QAEngine
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.merge_localization import MergeLocalizationStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    ResolveAssetsSymbolsStage,
)
from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage

# -- helpers -----------------------------------------------------------------


class _MockGateway(LlmGateway):
    def translate(
        self, system_prompt: str, user_prompt: str, model_profile: ModelProfile
    ) -> LlmResponse:
        data = json.loads(user_prompt)
        translations = [
            {"inline_id": n["inline_id"], "ru_text": f"[RU] {n['source_text']}"}
            for n in data["text_nodes"]
        ]
        return LlmResponse(
            text=json.dumps({"unit_id": data["unit_id"], "translations": translations}),
            provider="mock",
            model="mock",
        )

    def provider_name(self) -> str:
        return "mock"


def _create_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    qa_gate: QAGateConfig | None = None,
    skip_qa_gate: bool = False,
) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = configs_root.parent / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-001", ["test-doc"])

    rule_profile = RuleProfile(profile_id="test")
    if qa_gate is not None:
        rule_profile = rule_profile.model_copy(update={"qa_gate": qa_gate})

    return StageContext(
        run_id="run-001",
        doc_id="test-doc",
        pipeline_config=PipelineConfig(run_id="run-001", skip_qa_gate=skip_qa_gate),
        document_config=DocumentConfig(
            doc_id="test-doc",
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test Doc", ru="\u0422\u0435\u0441\u0442"),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=rule_profile,
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


def _run_through_enrich(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)
    ctx.llm_gateway = _MockGateway()
    TranslateUnitsStage().execute(ctx)
    MergeLocalizationStage().execute(ctx)
    EnrichContentStage().execute(ctx)


def _make_issue(
    severity: str = "warning",
    rule_id: str = "test.rule",
    category: str = "test",
) -> QAIssue:
    return QAIssue(
        rule_id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        category=category,
        message="test issue",
    )


# -- QAGateConfig tests -----------------------------------------------------


class TestQAGateConfig:
    def test_default_values(self) -> None:
        config = QAGateConfig()
        assert config.enabled is True
        assert config.max_errors == 0
        assert config.max_warnings == 50

    def test_custom_thresholds(self) -> None:
        config = QAGateConfig(enabled=False, max_errors=5, max_warnings=100)
        assert config.enabled is False
        assert config.max_errors == 5
        assert config.max_warnings == 100


# -- Engine summarize with gate_config --------------------------------------


class TestSummarizeWithGateConfig:
    def test_gate_config_overrides_max_warnings(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("warning") for _ in range(10)]
        gate = QAGateConfig(max_warnings=5)
        summary = engine.summarize("doc-1", issues, gate_config=gate)
        assert summary.accepted is False
        assert "10 warnings exceed threshold (5)" in summary.rejection_reasons[0]

    def test_gate_config_max_errors_allows_some(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("error") for _ in range(3)]
        gate = QAGateConfig(max_errors=5)
        summary = engine.summarize("doc-1", issues, gate_config=gate)
        assert summary.accepted is True

    def test_gate_config_max_errors_rejects(self) -> None:
        engine = QAEngine()
        issues = [_make_issue("error") for _ in range(6)]
        gate = QAGateConfig(max_errors=5)
        summary = engine.summarize("doc-1", issues, gate_config=gate)
        assert summary.accepted is False
        assert "6 error(s) exceed threshold (5)" in summary.rejection_reasons[0]

    def test_gate_config_at_boundary_accepted(self) -> None:
        """Exactly max_errors errors should still be accepted."""
        engine = QAEngine()
        issues = [_make_issue("error") for _ in range(5)]
        gate = QAGateConfig(max_errors=5)
        summary = engine.summarize("doc-1", issues, gate_config=gate)
        assert summary.accepted is True

    def test_legacy_max_warnings_still_works(self) -> None:
        """When no gate_config, the legacy max_warnings param is used."""
        engine = QAEngine()
        issues = [_make_issue("warning") for _ in range(10)]
        summary = engine.summarize("doc-1", issues, max_warnings=5)
        assert summary.accepted is False


# -- Category breakdown -----------------------------------------------------


class TestCategoryBreakdown:
    def test_breakdown_single_category(self) -> None:
        engine = QAEngine()
        issues = [
            _make_issue("error", category="translation"),
            _make_issue("warning", category="translation"),
            _make_issue("info", category="translation"),
        ]
        summary = engine.summarize("doc-1", issues)
        assert len(summary.by_category) == 1
        cat = summary.by_category[0]
        assert cat.category == "translation"
        assert cat.errors == 1
        assert cat.warnings == 1
        assert cat.infos == 1

    def test_breakdown_multiple_categories(self) -> None:
        engine = QAEngine()
        issues = [
            _make_issue("error", category="translation"),
            _make_issue("warning", category="layout"),
        ]
        summary = engine.summarize("doc-1", issues)
        assert len(summary.by_category) == 2
        categories = {c.category for c in summary.by_category}
        assert categories == {"translation", "layout"}

    def test_breakdown_empty_issues(self) -> None:
        engine = QAEngine()
        summary = engine.summarize("doc-1", [])
        assert summary.by_category == []


# -- QualityGateError -------------------------------------------------------


class TestQualityGateError:
    def test_error_message(self) -> None:
        summary = QASummary(
            doc_id="doc-1",
            errors=2,
            accepted=False,
            rejection_reasons=["2 error(s) exceed threshold (0)"],
        )
        err = QualityGateError(summary)
        assert "doc-1" in str(err)
        assert "2 error(s) exceed threshold (0)" in str(err)
        assert err.summary is summary

    def test_error_is_exception(self) -> None:
        summary = QASummary(doc_id="doc-1", accepted=False, rejection_reasons=["bad"])
        assert isinstance(QualityGateError(summary), Exception)


# -- Stage integration tests -------------------------------------------------


class TestEvaluateQAStageGate:
    def test_passes_when_quality_ok(self, tmp_path: Path) -> None:
        """With mock translations, QA gate should pass (no errors)."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_enrich(ctx)

        # Should not raise
        EvaluateQAStage().execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "evaluate_qa",
            "summary.json",
            QASummary,
        )
        assert summary.accepted is True
        assert summary.gate_skipped is False

    def test_gate_skipped_flag_persisted(self, tmp_path: Path) -> None:
        """skip_qa_gate=True records gate_skipped=True in summary."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf, skip_qa_gate=True)
        _run_through_enrich(ctx)

        EvaluateQAStage().execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "evaluate_qa",
            "summary.json",
            QASummary,
        )
        assert summary.gate_skipped is True

    def test_gate_disabled_does_not_raise(self, tmp_path: Path) -> None:
        """When qa_gate.enabled=False, stage never raises."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        gate = QAGateConfig(enabled=False, max_errors=0, max_warnings=0)
        ctx = _make_context(tmp_path, pdf, qa_gate=gate)
        _run_through_enrich(ctx)

        # Should not raise even with max_warnings=0
        EvaluateQAStage().execute(ctx)

    def test_skip_qa_gate_prevents_failure(self, tmp_path: Path) -> None:
        """skip_qa_gate=True prevents stage from raising on rejection."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        gate = QAGateConfig(enabled=True, max_errors=0, max_warnings=0)
        ctx = _make_context(tmp_path, pdf, qa_gate=gate, skip_qa_gate=True)
        _run_through_enrich(ctx)

        # Should not raise
        EvaluateQAStage().execute(ctx)

    def test_summary_has_by_category(self, tmp_path: Path) -> None:
        """Summary includes by_category breakdown."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_enrich(ctx)
        EvaluateQAStage().execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "evaluate_qa",
            "summary.json",
            QASummary,
        )
        assert isinstance(summary.by_category, list)


class TestPipelineConfigSkipQaGate:
    def test_default_false(self) -> None:
        config = PipelineConfig(run_id="test")
        assert config.skip_qa_gate is False

    def test_set_true(self) -> None:
        config = PipelineConfig(run_id="test", skip_qa_gate=True)
        assert config.skip_qa_gate is True


class TestRuleProfileQAGate:
    def test_default_qa_gate(self) -> None:
        profile = RuleProfile(profile_id="test")
        assert profile.qa_gate.enabled is True
        assert profile.qa_gate.max_errors == 0
        assert profile.qa_gate.max_warnings == 50
