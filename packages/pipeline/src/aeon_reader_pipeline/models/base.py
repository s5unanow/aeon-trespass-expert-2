"""Base artifact envelope and provenance models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceSpanRef(BaseModel):
    """Reference to a source PDF span."""

    page_number: int
    block_index: int | None = None
    line_index: int | None = None
    span_index: int | None = None
    bbox_pt: tuple[float, float, float, float] | None = None


class LlmCallRef(BaseModel):
    """Reference to an LLM call for provenance tracking."""

    provider: str
    model_id: str
    model_profile_id: str
    prompt_bundle_id: str
    prompt_hash: str
    request_hash: str
    response_hash: str
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int
    retry_count: int = 0
    timestamp: datetime


class Provenance(BaseModel):
    """Lineage and reproducibility metadata."""

    source_pdf_sha256: str
    source_page_number: int | None = None
    source_span_refs: list[SourceSpanRef] = Field(default_factory=list)
    parent_artifact_ids: list[str] = Field(default_factory=list)
    created_by_stage: str
    stage_version: str
    run_id: str
    config_hashes: dict[str, str] = Field(default_factory=dict)
    llm_call: LlmCallRef | None = None
    notes: dict[str, Any] = Field(default_factory=dict)


class ArtifactEnvelope(BaseModel):
    """Standard wrapper for every persisted artifact."""

    schema_name: str
    schema_version: str
    artifact_id: str
    run_id: str
    stage: str
    stage_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str
    provenance: Provenance
