"""Tests for ArtifactStore and JSON IO."""

from pathlib import Path

import pytest

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.io.json_io import (
    append_jsonl,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)
from aeon_reader_pipeline.models.run_models import RunManifest, StageManifest, WorkUnitStatus


def test_write_read_json_roundtrip(tmp_path: Path):
    manifest = RunManifest(run_id="test-001", doc_ids=["doc-a"])
    path = tmp_path / "manifest.json"
    write_json(path, manifest)
    loaded = read_json(path, RunManifest)
    assert loaded.run_id == "test-001"
    assert loaded.doc_ids == ["doc-a"]


def test_write_read_jsonl_roundtrip(tmp_path: Path):
    units = [
        WorkUnitStatus(unit_id="u001", status="completed"),
        WorkUnitStatus(unit_id="u002", status="failed", error="timeout"),
    ]
    path = tmp_path / "units.jsonl"
    write_jsonl(path, units)
    loaded = read_jsonl(path, WorkUnitStatus)
    assert len(loaded) == 2
    assert loaded[0].unit_id == "u001"
    assert loaded[1].status == "failed"


def test_append_jsonl(tmp_path: Path):
    path = tmp_path / "log.jsonl"
    append_jsonl(path, WorkUnitStatus(unit_id="u001"))
    append_jsonl(path, WorkUnitStatus(unit_id="u002"))
    loaded = read_jsonl(path, WorkUnitStatus)
    assert len(loaded) == 2


def test_read_missing_json(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "missing.json", RunManifest)


def test_artifact_store_create_run(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    manifest = store.create_run("run-001", ["doc-a", "doc-b"])
    assert manifest.run_id == "run-001"
    assert manifest.status == "running"
    assert (tmp_path / "runs" / "run-001" / "doc-a").is_dir()
    assert (tmp_path / "runs" / "run-001" / "doc-b").is_dir()
    assert (tmp_path / "runs" / "run-001" / "run_manifest.json").exists()


def test_artifact_store_load_run_manifest(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    store.create_run("run-002", ["doc-a"])
    loaded = store.load_run_manifest("run-002")
    assert loaded.run_id == "run-002"


def test_artifact_store_stage_manifest(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    store.create_run("run-003", ["doc-a"])
    stage_manifest = StageManifest(stage_name="ingest_source", stage_version="0.1.0")
    store.save_stage_manifest("run-003", "doc-a", stage_manifest)
    loaded = store.load_stage_manifest("run-003", "doc-a", "ingest_source")
    assert loaded is not None
    assert loaded.stage_name == "ingest_source"


def test_artifact_store_stage_manifest_missing(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    result = store.load_stage_manifest("missing", "doc", "ingest_source")
    assert result is None


def test_artifact_store_write_read_artifact(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    store.create_run("run-004", ["doc-a"])
    manifest = RunManifest(run_id="test")
    path = store.write_artifact("run-004", "doc-a", "ingest_source", "test.json", manifest)
    assert path.exists()
    loaded = store.read_artifact("run-004", "doc-a", "ingest_source", "test.json", RunManifest)
    assert loaded.run_id == "test"


def test_artifact_store_stage_dir_prefix(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    d = store.stage_dir("run-001", "doc-a", "normalize_layout")
    assert "03_normalize" in str(d)


def test_artifact_store_unknown_stage(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="Unknown stage"):
        store.stage_dir("run-001", "doc-a", "unknown_stage")
