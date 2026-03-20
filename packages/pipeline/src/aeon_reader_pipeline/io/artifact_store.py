"""Centralized artifact store for pipeline runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from aeon_reader_pipeline.io.json_io import read_json, read_jsonl, write_json, write_jsonl
from aeon_reader_pipeline.models.run_models import RunManifest, StageManifest

T = TypeVar("T", bound=BaseModel)


class ArtifactStore:
    """Manages reading and writing of versioned artifacts within run directories."""

    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root

    @property
    def runs_root(self) -> Path:
        """Root directory for all runs."""
        return self.artifact_root / "runs"

    @property
    def cache_root(self) -> Path:
        """Root directory for cache."""
        return self.artifact_root / "cache"

    @property
    def state_root(self) -> Path:
        """Root directory for state."""
        return self.artifact_root / "state"

    def run_dir(self, run_id: str, doc_id: str) -> Path:
        """Get the directory for a specific run and document."""
        return self.runs_root / run_id / doc_id

    def stage_dir(self, run_id: str, doc_id: str, stage_name: str) -> Path:
        """Get the directory for a specific stage within a run."""
        stage_prefix = _stage_prefix(stage_name)
        return self.run_dir(run_id, doc_id) / stage_prefix

    def ensure_stage_dir(self, run_id: str, doc_id: str, stage_name: str) -> Path:
        """Create and return the stage directory."""
        d = self.stage_dir(run_id, doc_id, stage_name)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_run(self, run_id: str, doc_ids: list[str]) -> RunManifest:
        """Create a new run directory structure and initial manifest."""
        manifest = RunManifest(
            run_id=run_id,
            doc_ids=doc_ids,
            started_at=datetime.now(UTC),
            status="running",
        )
        for doc_id in doc_ids:
            run_path = self.run_dir(run_id, doc_id)
            run_path.mkdir(parents=True, exist_ok=True)
        manifest_path = self.runs_root / run_id / "run_manifest.json"
        write_json(manifest_path, manifest)
        return manifest

    def load_run_manifest(self, run_id: str) -> RunManifest:
        """Load an existing run manifest."""
        path = self.runs_root / run_id / "run_manifest.json"
        return read_json(path, RunManifest)

    def save_run_manifest(self, manifest: RunManifest) -> None:
        """Save/update a run manifest."""
        path = self.runs_root / manifest.run_id / "run_manifest.json"
        write_json(path, manifest)

    def save_stage_manifest(self, run_id: str, doc_id: str, manifest: StageManifest) -> None:
        """Save a stage manifest."""
        stage_dir = self.ensure_stage_dir(run_id, doc_id, manifest.stage_name)
        write_json(stage_dir / "stage_manifest.json", manifest)

    def load_stage_manifest(
        self, run_id: str, doc_id: str, stage_name: str
    ) -> StageManifest | None:
        """Load a stage manifest if it exists."""
        stage_dir = self.stage_dir(run_id, doc_id, stage_name)
        path = stage_dir / "stage_manifest.json"
        if not path.exists():
            return None
        return read_json(path, StageManifest)

    def write_artifact(
        self,
        run_id: str,
        doc_id: str,
        stage_name: str,
        filename: str,
        model: BaseModel,
    ) -> Path:
        """Write a typed artifact to the stage directory."""
        stage_dir = self.ensure_stage_dir(run_id, doc_id, stage_name)
        path = stage_dir / filename
        write_json(path, model)
        return path

    def write_artifact_list(
        self,
        run_id: str,
        doc_id: str,
        stage_name: str,
        filename: str,
        models: list[BaseModel],
    ) -> Path:
        """Write a list of models as JSONL to the stage directory."""
        stage_dir = self.ensure_stage_dir(run_id, doc_id, stage_name)
        path = stage_dir / filename
        write_jsonl(path, models)
        return path

    def read_artifact(
        self,
        run_id: str,
        doc_id: str,
        stage_name: str,
        filename: str,
        model_cls: type[T],
    ) -> T:
        """Read a typed artifact from the stage directory."""
        stage_dir = self.stage_dir(run_id, doc_id, stage_name)
        path = stage_dir / filename
        return read_json(path, model_cls)

    def read_artifact_list(
        self,
        run_id: str,
        doc_id: str,
        stage_name: str,
        filename: str,
        model_cls: type[T],
    ) -> list[T]:
        """Read a JSONL artifact from the stage directory."""
        stage_dir = self.stage_dir(run_id, doc_id, stage_name)
        path = stage_dir / filename
        return read_jsonl(path, model_cls)

    def cache_dir_for(self, stage_name: str, cache_key: str) -> Path:
        """Get cache directory for a specific stage and cache key."""
        return self.cache_root / stage_name / cache_key


# Stage name to directory prefix mapping
_STAGE_PREFIXES: dict[str, str] = {
    "resolve_run": "00_resolve",
    "ingest_source": "01_ingest",
    "extract_primitives": "02_extract",
    "collect_evidence": "02a_evidence",
    "resolve_page_ir": "02b_resolve_ir",
    "normalize_layout": "03_normalize",
    "resolve_assets_symbols": "04_assets",
    "plan_translation": "05_translation_plan",
    "translate_units": "06_translate",
    "merge_localization": "07_localize",
    "enrich_content": "08_enrich",
    "evaluate_qa": "09_qa",
    "export_site_bundle": "11_export",
    "build_reader": "12_site",
    "index_search": "13_search",
    "package_release": "14_release",
}


def _stage_prefix(stage_name: str) -> str:
    """Get the directory prefix for a stage."""
    if stage_name not in _STAGE_PREFIXES:
        raise ValueError(
            f"Unknown stage: {stage_name}. Known stages: {list(_STAGE_PREFIXES.keys())}"
        )
    return _STAGE_PREFIXES[stage_name]
