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

# Cache modes that bypass the skip/resume check and always execute
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

    def _should_skip(
        self,
        ctx: StageContext,
        stage: BaseStage,
        cache_key: str,
    ) -> bool:
        """Determine if a stage should be skipped, respecting cache_mode.

        A stage is skipped only when *all* of the following hold:

        1. ``cache_mode`` is not a force-rerun mode.
        2. The stage itself reports it can be skipped (``should_skip()``).
        3. If a persisted manifest exists, the stored cache key matches the
           current ``cache_key`` (i.e. inputs have not changed).  When no
           manifest is found or the manifest predates cache-key tracking,
           the stage's own judgement is trusted.
        """
        cache_mode = ctx.pipeline_config.cache_mode
        if cache_mode in _FORCE_RERUN_MODES:
            return False

        if not stage.should_skip(ctx):
            return False

        # Stage says it can be skipped.  Validate the cache key when a
        # manifest is available — if inputs changed the stage must rerun.
        manifest = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, stage.name)
        if manifest is None:
            # No manifest to validate against — trust the stage.
            return True

        stored_key = str(manifest.metrics.get("cache_key", ""))
        if not stored_key:
            # Old manifest without cache key tracking — trust it.
            return True

        return stored_key == cache_key

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

        # Compute input hashes and cache key upfront so skip checks can
        # validate that persisted outputs were produced from the same inputs.
        input_hashes = self._compute_input_hashes(ctx)
        cache_key = stage_cache_key(
            stage_name=stage.name,
            stage_version=stage.version,
            **input_hashes,
        )

        # --- skip / cache-hit path ---
        if self._should_skip(ctx, stage, cache_key):
            stage_log.info("stage.skipped", reason="cache_hit")
            self._update_stage_status(ctx, stage.name, "skipped")
            self._increment_cache_stat(ctx, "hits")
            return

        # --- read_only mode: no valid cache → skip without executing ---
        if ctx.pipeline_config.cache_mode == "read_only":
            stage_log.warning("stage.skipped", reason="read_only_no_cache")
            self._update_stage_status(ctx, stage.name, "skipped")
            return

        # --- execute the stage ---
        stage_log.info("stage.start")
        self._update_stage_status(ctx, stage.name, "running")
        self._increment_cache_stat(ctx, "misses")

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
            collected_errors = ctx.errors.collect()
            collected_work_units = ctx.work_units.collect()

            # Compute output hashes from the files the stage wrote
            output_hashes = ctx.artifact_store.compute_output_hashes(
                ctx.run_id, ctx.doc_id, stage.name
            )

            stage_manifest.errors = collected_errors
            stage_manifest.work_units = collected_work_units
            stage_manifest.status = "completed"
            stage_manifest.completed_at = completed_at
            stage_manifest.output_hashes = output_hashes
            stage_manifest.metrics = {
                "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
                "cache_key": cache_key,
            }
            ctx.artifact_store.save_stage_manifest(ctx.run_id, ctx.doc_id, stage_manifest)
            self._update_stage_status(ctx, stage.name, "completed")
            if collected_errors:
                stage_log.info(
                    "stage.complete",
                    non_fatal_errors=len(collected_errors),
                )
            else:
                stage_log.info("stage.complete")
        except Exception as e:
            completed_at = datetime.now(UTC)
            collected_errors = ctx.errors.collect()
            collected_work_units = ctx.work_units.collect()
            stage_manifest.errors = collected_errors
            stage_manifest.work_units = collected_work_units
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

    def _increment_cache_stat(
        self,
        ctx: StageContext,
        stat: str,
    ) -> None:
        """Increment a cache statistics counter on the run manifest."""
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        manifest.cache_stats[stat] = manifest.cache_stats.get(stat, 0) + 1
        ctx.artifact_store.save_run_manifest(manifest)
