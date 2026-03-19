"""Pipeline runner — executes stages in order with manifest tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from aeon_reader_pipeline.cache.keys import stage_cache_key
from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.run_models import StageManifest, StageStatus
from aeon_reader_pipeline.stage_framework.base import BaseStage
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stage_framework.registry import (
    filter_stages,
    get_registered_stages,
    get_stage,
)

logger = structlog.get_logger()

# Cache modes that bypass the skip/resume check
_FORCE_RERUN_MODES = frozenset({"force_refresh", "off", "write_only"})


class PipelineRunner:
    """Executes pipeline stages in order with manifest tracking."""

    def run(self, ctx: StageContext) -> None:
        """Run the pipeline for a single document."""
        selected = filter_stages(
            from_stage=ctx.pipeline_config.stages.from_stage,
            to_stage=ctx.pipeline_config.stages.to_stage,
            only=ctx.pipeline_config.stages.only,
            exclude=ctx.pipeline_config.stages.exclude,
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

    def _should_skip(self, ctx: StageContext, stage: BaseStage) -> bool:
        """Determine if a stage should be skipped, respecting cache_mode."""
        cache_mode = ctx.pipeline_config.cache_mode
        if cache_mode in _FORCE_RERUN_MODES:
            return False
        return stage.should_skip(ctx)

    def _compute_input_hashes(self, ctx: StageContext) -> dict[str, str]:
        """Compute deterministic input hashes for a stage."""
        hashes: dict[str, str] = {
            "document_config": hash_model(ctx.document_config),
            "rule_profile": hash_model(ctx.rule_profile),
            "model_profile": hash_model(ctx.model_profile),
            "symbol_pack": hash_model(ctx.symbol_pack),
            "glossary_pack": hash_model(ctx.glossary_pack),
        }
        if ctx.patch_set is not None:
            hashes["patch_set"] = hash_model(ctx.patch_set)
        return hashes

    def _run_stage(
        self,
        ctx: StageContext,
        stage: BaseStage,
        log: Any,
    ) -> None:
        """Run a single stage with manifest tracking."""
        stage_log: Any = log.bind(stage=stage.name, stage_version=stage.version)

        # Check skip (respects cache_mode)
        if self._should_skip(ctx, stage):
            stage_log.info("stage.skipped")
            self._update_stage_status(ctx, stage.name, "skipped")
            return

        stage_log.info("stage.start")
        self._update_stage_status(ctx, stage.name, "running")

        # Compute input hashes and cache key
        input_hashes = self._compute_input_hashes(ctx)
        cache_key = stage_cache_key(
            stage_name=stage.name,
            stage_version=stage.version,
            **input_hashes,
        )

        # Create stage manifest
        started_at = datetime.now(UTC)
        stage_manifest = StageManifest(
            stage_name=stage.name,
            stage_version=stage.version,
            status="running",
            started_at=started_at,
            input_hashes=input_hashes,
        )

        try:
            stage.execute(ctx)
            completed_at = datetime.now(UTC)
            collected = ctx.errors.collect()
            stage_manifest.errors = collected
            stage_manifest.status = "completed"
            stage_manifest.completed_at = completed_at
            stage_manifest.metrics = {
                "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
                "cache_key": cache_key,
            }
            ctx.artifact_store.save_stage_manifest(ctx.run_id, ctx.doc_id, stage_manifest)
            self._update_stage_status(ctx, stage.name, "completed")
            if collected:
                stage_log.info(
                    "stage.complete",
                    non_fatal_errors=len(collected),
                )
            else:
                stage_log.info("stage.complete")
        except Exception as e:
            completed_at = datetime.now(UTC)
            collected = ctx.errors.collect()
            stage_manifest.errors = collected
            stage_manifest.status = "failed"
            stage_manifest.error = str(e)
            stage_manifest.completed_at = completed_at
            stage_manifest.metrics = {
                "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
                "cache_key": cache_key,
            }
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
