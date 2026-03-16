"""Stage 9 — evaluate quality assurance rules and produce QA report."""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.qa.engine import QAEngine
from aeon_reader_pipeline.qa.rules.translation_rules import (
    EmptyTranslationRule,
    MissingTranslationRule,
)
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import register_stage
from aeon_reader_pipeline.stages.enrich_content import NavigationTree

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

        ctx.logger.info("evaluating_qa", page_count=manifest.page_count)

        # Load enriched pages
        pages: list[PageRecord] = []
        for page_num in range(1, manifest.page_count + 1):
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
        max_warnings = ctx.rule_profile.release.max_warnings
        summary = engine.summarize(ctx.doc_id, issues, max_warnings)
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
        )
