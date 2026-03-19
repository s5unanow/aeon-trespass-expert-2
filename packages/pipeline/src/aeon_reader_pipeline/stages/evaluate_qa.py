"""Stage 9 — evaluate quality assurance rules and produce QA report."""

from __future__ import annotations

from aeon_reader_pipeline.models.enrich_models import NavigationTree
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.qa import QualityGateError
from aeon_reader_pipeline.qa.engine import QAEngine
from aeon_reader_pipeline.qa.rules.translation_rules import (
    EmptyTranslationRule,
    MissingTranslationRule,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage

STAGE_NAME = "evaluate_qa"
STAGE_VERSION = "1.0.0"


def _build_default_engine() -> QAEngine:
    """Create engine with default rule set."""
    engine = QAEngine()
    engine.register(MissingTranslationRule())
    engine.register(EmptyTranslationRule())
    return engine


@register_stage
class EvaluateQAStage(BaseStage):
    """Run QA rules on enriched content and produce acceptance summary."""

    name = STAGE_NAME
    version = STAGE_VERSION
    description = "Evaluate QA rules and produce acceptance summary"

    def execute(self, ctx: StageContext) -> None:
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "ingest_source",
            "document_manifest.json",
            DocumentManifest,
        )

        from aeon_reader_pipeline.utils.page_filter import pages_to_process

        page_nums = pages_to_process(manifest.page_count, ctx.pipeline_config.page_filter)
        ctx.logger.info("evaluating_qa", page_count=len(page_nums))

        # Load enriched pages
        pages: list[PageRecord] = []
        for page_num in page_nums:
            record = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "enrich_content",
                f"pages/p{page_num:04d}.json",
                PageRecord,
            )
            pages.append(record)

        # Load navigation
        nav: NavigationTree | None = None
        try:
            nav = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "enrich_content",
                "navigation.json",
                NavigationTree,
            )
        except FileNotFoundError:
            ctx.logger.warning("navigation_not_found")

        # Run QA engine
        engine = _build_default_engine()
        issues = engine.evaluate(pages, nav)

        # Write issues
        if issues:
            ctx.artifact_store.write_artifact_list(
                ctx.run_id,
                ctx.doc_id,
                STAGE_NAME,
                "issues.jsonl",
                list(issues),
            )

        # Build and write summary
        gate_config = ctx.rule_profile.qa_gate
        skip_gate = ctx.pipeline_config.skip_qa_gate
        summary = engine.summarize(
            ctx.doc_id,
            issues,
            gate_config=gate_config,
        )

        if skip_gate:
            summary = summary.model_copy(update={"gate_skipped": True})

        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            STAGE_NAME,
            "summary.json",
            summary,
        )

        ctx.logger.info(
            "qa_evaluation_complete",
            total_issues=summary.total_issues,
            errors=summary.errors,
            warnings=summary.warnings,
            accepted=summary.accepted,
            gate_skipped=skip_gate,
        )

        # Enforce quality gate
        if gate_config.enabled and not skip_gate and not summary.accepted:
            raise QualityGateError(summary)
