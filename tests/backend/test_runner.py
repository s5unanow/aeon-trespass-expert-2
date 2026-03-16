"""Tests for stage registry and pipeline runner."""

import pytest

from aeon_reader_pipeline.stage_framework.registry import (
    STAGE_ORDER,
    filter_stages,
    get_all_stages_ordered,
)


def test_stage_order_has_15_stages():
    assert len(STAGE_ORDER) == 15


def test_get_all_stages_ordered():
    stages = get_all_stages_ordered()
    assert stages[0] == "resolve_run"
    assert stages[-1] == "package_release"


def test_filter_stages_all():
    stages = filter_stages()
    assert stages == STAGE_ORDER


def test_filter_stages_from():
    stages = filter_stages(from_stage="normalize_layout")
    assert stages[0] == "normalize_layout"
    assert "ingest_source" not in stages


def test_filter_stages_to():
    stages = filter_stages(to_stage="extract_primitives")
    assert stages[-1] == "extract_primitives"
    assert "normalize_layout" not in stages


def test_filter_stages_from_to():
    stages = filter_stages(from_stage="extract_primitives", to_stage="normalize_layout")
    assert stages == ["extract_primitives", "normalize_layout"]


def test_filter_stages_only():
    stages = filter_stages(only=["ingest_source", "extract_primitives"])
    assert stages == ["ingest_source", "extract_primitives"]


def test_filter_stages_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        filter_stages(from_stage="nonexistent")


def test_filter_stages_only_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        filter_stages(only=["nonexistent"])
