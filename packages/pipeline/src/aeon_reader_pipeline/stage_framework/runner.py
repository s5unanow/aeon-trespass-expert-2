"""Pipeline runner — executes stages in order with manifest tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from aeon_reader_pipeline.models.run_models import StageManifest, StageStatus
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import (
    filter_stages,
    get_registered_stages,
    get_stage,
)

logger = structlog.get_logger()


class PipelineRunner:
    """Executes pipeline stages in order with manifest tracking."""

    def run(self, ctx: StageContext) -> None:
        """Run the pipeline for a single document."""
        selected = filter_stages(
            from_stage=ctx.pipeline_config.stages.from_stage,
            to_stage=ctx.pipeline_config.stages.to_stage,
            only=ctx.pipeline_config.stages.only,
        )

        registered = set(get_registered_stages())
        stages_to_run = [s for s in selected if s in registered]

        log: Any = logger.bind(run_id=ctx.run_id, doc_id=ctx.doc_id)
        log.info("pipeline.start", stages=stages_to_run)

        # Update run manifest with stage statuses
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        manifest.stages = [StageStatus(stage_name=name, status="pending") for name in stages_to_run]
        manifest.status = "running"
        ctx.artifact_store.save_run_manifest(manifest)

        for stage_name in stages_to_run:
            stage = get_stage(stage_name)
            self._run_stage(ctx, stage, log)

        # Mark run complete
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        manifest.status = "completed"
        manifest.completed_at = datetime.now(UTC)
        ctx.artifact_store.save_run_manifest(manifest)
        log.info("pipeline.complete")

    def _run_stage(
        self,
        ctx: StageContext,
        stage: BaseStage,
        log: Any,
    ) -> None:
        """Run a single stage with manifest tracking."""
        stage_log: Any = log.bind(stage=stage.name, stage_version=stage.version)

        # Check skip
        if stage.should_skip(ctx):
            stage_log.info("stage.skipped")
            self._update_stage_status(ctx, stage.name, "skipped")
            return

        stage_log.info("stage.start")
        self._update_stage_status(ctx, stage.name, "running")

        # Create stage manifest
        stage_manifest = StageManifest(
            stage_name=stage.name,
            stage_version=stage.version,
            status="running",
            started_at=datetime.now(UTC),
        )

        try:
            stage.execute(ctx)
            stage_manifest.status = "completed"
            stage_manifest.completed_at = datetime.now(UTC)
            ctx.artifact_store.save_stage_manifest(ctx.run_id, ctx.doc_id, stage_manifest)
            self._update_stage_status(ctx, stage.name, "completed")
            stage_log.info("stage.complete")
        except Exception as e:
            stage_manifest.status = "failed"
            stage_manifest.error = str(e)
            stage_manifest.completed_at = datetime.now(UTC)
            ctx.artifact_store.save_stage_manifest(ctx.run_id, ctx.doc_id, stage_manifest)
            self._update_stage_status(ctx, stage.name, "failed")
            stage_log.error("stage.failed", error=str(e))
            raise

    def _update_stage_status(
        self,
        ctx: StageContext,
        stage_name: str,
        status: str,
    ) -> None:
        """Update stage status in the run manifest."""
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        for s in manifest.stages:
            if s.stage_name == stage_name:
                s.status = status  # type: ignore[assignment]
                break
        ctx.artifact_store.save_run_manifest(manifest)
