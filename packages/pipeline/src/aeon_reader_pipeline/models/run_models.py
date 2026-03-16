"""Pipeline execution, run manifest, and stage manifest models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RetryPolicy(BaseModel):
    """Retry configuration."""

    max_attempts: int = 3
    backoff_seconds: list[int] = Field(default_factory=lambda: [1, 5, 15])


class StageSelector(BaseModel):
    """Stage filtering."""

    from_stage: str | None = None
    to_stage: str | None = None
    only: list[str] | None = None


class PipelineConfig(BaseModel):
    """Runtime execution policy."""

    run_id: str
    docs: list[str] = Field(default_factory=list)
    stages: StageSelector = Field(default_factory=StageSelector)
    cache_mode: Literal["read_write", "read_only", "write_only", "off", "force_refresh"] = (
        "read_write"
    )
    strict_mode: bool = False
    max_workers: int = 1
    llm_concurrency: int = 1
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    artifact_root: str = "artifacts"
    release_channel: Literal["dev", "preview", "prod"] = "dev"
    baseline_run_ref: str | None = None


class WorkUnitStatus(BaseModel):
    """Status of a single work unit (page, translation unit, etc.)."""

    unit_id: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cache_hit: bool = False


class StageManifest(BaseModel):
    """Stage-level status and work unit tracking."""

    stage_name: str
    stage_version: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    work_units: list[WorkUnitStatus] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ResolvedDocPlan(BaseModel):
    """Resolved plan for a single document."""

    doc_id: str
    source_pdf_path: str
    config_hash: str
    rule_profile_hash: str
    model_profile_hash: str
    symbol_pack_hash: str
    glossary_pack_hash: str
    patch_set_hash: str | None = None
    prompt_bundle_hash: str | None = None


class ResolvedRunPlan(BaseModel):
    """Fully resolved run plan."""

    run_id: str
    docs: list[ResolvedDocPlan] = Field(default_factory=list)
    stage_plan: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


class StageStatus(BaseModel):
    """Stage status entry in run manifest."""

    stage_name: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"


class RunManifest(BaseModel):
    """Run-level metadata."""

    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    doc_ids: list[str] = Field(default_factory=list)
    stages: list[StageStatus] = Field(default_factory=list)
    config_hashes: dict[str, str] = Field(default_factory=dict)
    git_commit: str | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    cache_stats: dict[str, int] = Field(default_factory=lambda: {"hits": 0, "misses": 0})
    qa_acceptance: bool | None = None
    pipeline_config: PipelineConfig | None = None
