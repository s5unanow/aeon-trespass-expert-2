"""Tests for run and manifest models."""

from aeon_reader_pipeline.models.run_models import (
    PipelineConfig,
    ResolvedRunPlan,
    RunManifest,
    StageManifest,
    StageSelector,
    WorkUnitStatus,
)


def test_pipeline_config_defaults():
    config = PipelineConfig(run_id="test-001")
    assert config.cache_mode == "read_write"
    assert config.strict_mode is False
    assert config.max_workers == 1


def test_stage_manifest_roundtrip():
    sm = StageManifest(stage_name="ingest_source", stage_version="0.1.0", status="completed")
    data = sm.model_dump(mode="json")
    loaded = StageManifest.model_validate(data)
    assert loaded.stage_name == "ingest_source"
    assert loaded.status == "completed"


def test_run_manifest_roundtrip():
    rm = RunManifest(run_id="run-001", doc_ids=["doc-a"])
    data = rm.model_dump(mode="json")
    loaded = RunManifest.model_validate(data)
    assert loaded.run_id == "run-001"


def test_work_unit_status():
    wu = WorkUnitStatus(unit_id="p0001", status="completed", cache_hit=True)
    assert wu.cache_hit is True


def test_resolved_run_plan():
    plan = ResolvedRunPlan(
        run_id="run-001",
        stage_plan=["ingest_source", "extract_primitives"],
    )
    assert len(plan.stage_plan) == 2


def test_stage_selector():
    sel = StageSelector(from_stage="extract_primitives", to_stage="normalize_layout")
    assert sel.from_stage == "extract_primitives"
