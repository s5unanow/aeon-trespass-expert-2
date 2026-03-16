"""Tests for state store."""

from pathlib import Path

from aeon_reader_pipeline.io.state_store import StateStore


def test_get_set_accepted_run(tmp_path: Path):
    store = StateStore(tmp_path / "state")
    assert store.get_accepted_run("doc-a") is None
    store.set_accepted_run("doc-a", "run-001")
    assert store.get_accepted_run("doc-a") == "run-001"


def test_get_set_baseline(tmp_path: Path):
    store = StateStore(tmp_path / "state")
    assert store.get_baseline("doc-a") is None
    store.set_baseline("doc-a", "run-001")
    assert store.get_baseline("doc-a") == "run-001"


def test_state_persists(tmp_path: Path):
    state_root = tmp_path / "state"
    store1 = StateStore(state_root)
    store1.set_accepted_run("doc-a", "run-001")
    store2 = StateStore(state_root)
    assert store2.get_accepted_run("doc-a") == "run-001"
