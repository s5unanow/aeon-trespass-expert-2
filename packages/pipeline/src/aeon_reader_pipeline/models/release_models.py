"""Release packaging and versioned distribution models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ReleaseDocEntry(BaseModel):
    """Single document included in a release."""

    doc_id: str
    page_count: int = 0
    qa_accepted: bool = True
    translation_coverage: float = 0.0


class ReleaseManifest(BaseModel):
    """Metadata for a packaged release.

    Lives at 14_release/release_manifest.json.
    The package stage does not decide acceptance — it enforces it.
    """

    release_id: str
    run_id: str
    documents: list[ReleaseDocEntry] = Field(default_factory=list)
    total_documents: int = 0
    all_accepted: bool = True
    rejection_reasons: list[str] = Field(default_factory=list)
    artifact_path: str | None = None
    artifact_size_bytes: int | None = None
    artifact_sha256: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    stage_version: str = "1.0.0"
