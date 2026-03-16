#!/usr/bin/env python3
"""Sync exported site bundle into apps/reader/generated/.

Copies the exported bundle for selected documents from the pipeline artifact
store into the reader's local generated directory. Wipes the target doc folder
before syncing to ensure a clean state.

Usage:
    uv run python scripts/sync_generated_bundle.py \\
        --artifacts-root artifacts \\
        --run <run_id> \\
        --doc <doc_id> [--doc <doc_id2>] \\
        --target apps/reader/generated
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def sync_bundle(
    artifacts_root: Path,
    run_id: str,
    doc_ids: list[str],
    target: Path,
) -> list[Path]:
    """Sync exported bundles for given docs into the target directory.

    Returns list of synced doc directories.
    """
    synced: list[Path] = []

    for doc_id in doc_ids:
        source = (
            artifacts_root
            / "runs"
            / run_id
            / doc_id
            / "11_export"
            / "site_bundle"
            / doc_id
        )
        if not source.exists():
            print(f"ERROR: Bundle not found at {source}", file=sys.stderr)
            sys.exit(1)

        dest = target / doc_id
        # Wipe target doc folder before sync
        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(source, dest)
        synced.append(dest)
        print(f"Synced {doc_id}: {source} -> {dest}")

    return synced


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync exported site bundle")
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
        help="Root of artifact store",
    )
    parser.add_argument("--run", required=True, help="Run ID")
    parser.add_argument(
        "--doc", action="append", required=True, help="Document ID(s) to sync"
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("apps/reader/generated"),
        help="Target directory for synced bundles",
    )
    args = parser.parse_args()

    args.target.mkdir(parents=True, exist_ok=True)
    synced = sync_bundle(args.artifacts_root, args.run, args.doc, args.target)
    print(f"Done: {len(synced)} document(s) synced.")


if __name__ == "__main__":
    main()
