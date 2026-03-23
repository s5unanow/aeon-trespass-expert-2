"""Pipeline runner — executes stages in order with manifest tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from aeon_reader_pipeline.cache.keys import stage_cache_key
from aeon_reader_pipeline.config.hashing import hash_model
from aeon_reader_pipeline.models.run_models import (
    RunManifest,
    RunSummary,
    StageManifest,
    StageStatus,
    StageSummary,
)
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

        try:
            for stage_name in stages_to_run:
                stage = get_stage(stage_name)
                self._run_stage(ctx, stage, log)
        except Exception as exc:
            try:
                manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
                manifest.status = "failed"
                manifest.completed_at = datetime.now(UTC)
                ctx.artifact_store.save_run_manifest(manifest)
                self._write_run_summary(ctx, manifest)
            except Exception:
                log.exception("pipeline.failed_to_write_failure_summary")
            log.error("pipeline.failed", error=str(exc))
            raise

        # Mark run complete
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        manifest.status = "completed"
        manifest.completed_at = datetime.now(UTC)
        ctx.artifact_store.save_run_manifest(manifest)
        self._write_run_summary(ctx, manifest)
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
        # Note: when no manifest exists, we trust the stage.  For the
        # default BaseStage.should_skip() this branch is unreachable
        # (it already returns False when no manifest exists), but custom
        # overrides may reach it.
        manifest = ctx.artifact_store.load_stage_manifest(ctx.run_id, ctx.doc_id, stage.name)
        if manifest is None:
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
            self._update_stage_status(ctx, stage.name, "skipped", cache_stat="hits")
            return

        # --- read_only mode: no valid cache → skip without executing ---
        if ctx.pipeline_config.cache_mode == "read_only":
            stage_log.warning("stage.skipped", reason="read_only_no_cache")
            self._update_stage_status(ctx, stage.name, "skipped", cache_stat="misses")
            return

        # --- execute the stage ---
        stage_log.info("stage.start")
        self._update_stage_status(ctx, stage.name, "running", cache_stat="misses")

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
        *,
        cache_stat: str | None = None,
    ) -> None:
        """Update stage status in the run manifest.

        Optionally increments a cache statistics counter in the same
        load/save cycle to avoid redundant I/O.
        """
        manifest = ctx.artifact_store.load_run_manifest(ctx.run_id)
        for s in manifest.stages:
            if s.stage_name == stage_name:
                s.status = status  # type: ignore[assignment]
                break
        if cache_stat is not None:
            manifest.cache_stats[cache_stat] = manifest.cache_stats.get(cache_stat, 0) + 1
        ctx.artifact_store.save_run_manifest(manifest)

    def _write_run_summary(self, ctx: StageContext, manifest: RunManifest) -> None:
        """Build and persist a consolidated run summary."""
        stage_summaries: list[StageSummary] = []
        pages_processed = 0
        pages_cached = 0
        pages_failed = 0

        for stage_status in manifest.stages:
            sm = ctx.artifact_store.load_stage_manifest(
                ctx.run_id, ctx.doc_id, stage_status.stage_name
            )
            duration_ms = 0
            if sm is not None:
                duration_ms = int(sm.metrics.get("duration_ms", 0) or 0)
                for wu in sm.work_units:
                    if wu.status == "completed":
                        pages_processed += 1
                    if wu.cache_hit:
                        pages_cached += 1
                    if wu.status == "failed":
                        pages_failed += 1

            stage_summaries.append(
                StageSummary(
                    name=stage_status.stage_name,
                    status=stage_status.status,
                    duration_ms=duration_ms,
                )
            )

        duration_s = 0.0
        if manifest.completed_at is not None:
            duration_s = round((manifest.completed_at - manifest.started_at).total_seconds(), 1)

        summary = RunSummary(
            run_id=manifest.run_id,
            document_id=ctx.doc_id,
            status=manifest.status,
            edition=ctx.document_config.edition,
            pages_processed=pages_processed,
            pages_cached=pages_cached,
            pages_failed=pages_failed,
            stages=stage_summaries,
            cache_stats=manifest.cache_stats,
            duration_s=duration_s,
            started_at=manifest.started_at,
            finished_at=manifest.completed_at,
            git_commit=manifest.git_commit,
        )

        ctx.artifact_store.save_run_summary(ctx.run_id, summary)
