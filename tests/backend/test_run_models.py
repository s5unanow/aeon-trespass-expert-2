"""Tests for run and manifest models."""

import pytest
from pydantic import ValidationError

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


def test_pipeline_config_extracted_constants_defaults():
    """New config fields have defaults matching previously hardcoded values."""
    config = PipelineConfig(run_id="test-001")
    assert config.translation_max_retries == 3
    assert config.max_nodes_per_unit == 20
    assert config.context_window_chars == 200
    assert config.progress_log_interval == 50


def test_pipeline_config_extracted_constants_custom():
    """New config fields accept custom values."""
    config = PipelineConfig(
        run_id="test-001",
        translation_max_retries=5,
        max_nodes_per_unit=30,
        context_window_chars=500,
        progress_log_interval=100,
    )
    assert config.translation_max_retries == 5
    assert config.max_nodes_per_unit == 30
    assert config.context_window_chars == 500
    assert config.progress_log_interval == 100


def test_pipeline_config_extracted_constants_validation():
    """Extracted config fields reject invalid values."""
    with pytest.raises(ValidationError):
        PipelineConfig(run_id="test-001", translation_max_retries=0)
    with pytest.raises(ValidationError):
        PipelineConfig(run_id="test-001", max_nodes_per_unit=0)
    with pytest.raises(ValidationError):
        PipelineConfig(run_id="test-001", context_window_chars=-1)
    with pytest.raises(ValidationError):
        PipelineConfig(run_id="test-001", progress_log_interval=0)


def test_pipeline_config_roundtrip_with_extracted_constants():
    """Extracted constants survive JSON serialization roundtrip."""
    config = PipelineConfig(
        run_id="test-001",
        translation_max_retries=5,
        max_nodes_per_unit=30,
        context_window_chars=500,
        progress_log_interval=100,
    )
    data = config.model_dump(mode="json")
    loaded = PipelineConfig.model_validate(data)
    assert loaded.translation_max_retries == 5
    assert loaded.max_nodes_per_unit == 30
    assert loaded.context_window_chars == 500
    assert loaded.progress_log_interval == 100


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
