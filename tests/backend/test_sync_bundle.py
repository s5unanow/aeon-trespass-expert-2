"""Tests for the sync_generated_bundle script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.sync_generated_bundle import sync_bundle


class TestSyncBundle:
    def test_syncs_exported_bundle(self, tmp_path: Path) -> None:
        # Set up a fake exported bundle
        artifacts_root = tmp_path / "artifacts"
        source = (
            artifacts_root
            / "runs"
            / "run-001"
            / "test-doc"
            / "11_export"
            / "site_bundle"
            / "test-doc"
        )
        source.mkdir(parents=True)
        (source / "bundle_manifest.json").write_text(
            json.dumps({"doc_id": "test-doc"})
        )
        pages = source / "pages"
        pages.mkdir()
        (pages / "p0001.json").write_text(json.dumps({"page_number": 1}))

        target = tmp_path / "generated"
        synced = sync_bundle(artifacts_root, "run-001", ["test-doc"], target)

        assert len(synced) == 1
        assert (target / "test-doc" / "bundle_manifest.json").exists()
        assert (target / "test-doc" / "pages" / "p0001.json").exists()

    def test_wipes_target_before_sync(self, tmp_path: Path) -> None:
        # Set up stale target
        target = tmp_path / "generated"
        stale = target / "test-doc"
        stale.mkdir(parents=True)
        (stale / "old_file.txt").write_text("stale")

        # Set up source
        artifacts_root = tmp_path / "artifacts"
        source = (
            artifacts_root
            / "runs"
            / "run-001"
            / "test-doc"
            / "11_export"
            / "site_bundle"
            / "test-doc"
        )
        source.mkdir(parents=True)
        (source / "bundle_manifest.json").write_text("{}")

        sync_bundle(artifacts_root, "run-001", ["test-doc"], target)

        assert not (target / "test-doc" / "old_file.txt").exists()
        assert (target / "test-doc" / "bundle_manifest.json").exists()

    def test_syncs_multiple_docs(self, tmp_path: Path) -> None:
        artifacts_root = tmp_path / "artifacts"
        for doc_id in ["doc-a", "doc-b"]:
            source = (
                artifacts_root
                / "runs"
                / "run-001"
                / doc_id
                / "11_export"
                / "site_bundle"
                / doc_id
            )
            source.mkdir(parents=True)
            (source / "bundle_manifest.json").write_text(
                json.dumps({"doc_id": doc_id})
            )

        target = tmp_path / "generated"
        synced = sync_bundle(artifacts_root, "run-001", ["doc-a", "doc-b"], target)

        assert len(synced) == 2
        assert (target / "doc-a" / "bundle_manifest.json").exists()
        assert (target / "doc-b" / "bundle_manifest.json").exists()
