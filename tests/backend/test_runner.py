"""Tests for stage registry and pipeline runner."""

import pytest

from aeon_reader_pipeline.stage_framework.registry import (
    STAGE_ORDER,
    filter_stages,
    get_all_stages_ordered,
    get_registered_stages,
)


def test_stage_order_has_15_stages():
    assert len(STAGE_ORDER) == 15


def test_get_all_stages_ordered():
    stages = get_all_stages_ordered()
    assert stages[0] == "resolve_run"
    assert stages[-1] == "package_release"


def test_all_stages_registered():
    """Every stage in STAGE_ORDER must be registered after importing stages."""
    import aeon_reader_pipeline.stages  # noqa: F401

    registered = set(get_registered_stages())
    for name in STAGE_ORDER:
        assert name in registered, f"Stage '{name}' is not registered"


def test_resolve_run_is_first_registered_stage():
    """resolve_run must be first in the registered stage order."""
    import aeon_reader_pipeline.stages  # noqa: F401

    registered = get_registered_stages()
    assert registered[0] == "resolve_run"


def test_filter_from_resolve_run_includes_all():
    """Starting from resolve_run includes all 15 stages."""
    stages = filter_stages(from_stage="resolve_run")
    assert stages == STAGE_ORDER
    assert len(stages) == 15


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
