"""State pointer management for accepted runs and baselines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aeon_reader_pipeline.io.json_io import read_raw_json, write_raw_json


class StateStore:
    """Manages state pointers outside of individual runs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.state_root.mkdir(parents=True, exist_ok=True)

    def get_accepted_run(self, doc_id: str) -> str | None:
        """Get the accepted run ID for a document."""
        data = self._load_state("accepted_runs.json")
        return data.get(doc_id)

    def set_accepted_run(self, doc_id: str, run_id: str) -> None:
        """Set the accepted run ID for a document."""
        data = self._load_state("accepted_runs.json")
        data[doc_id] = run_id
        self._save_state("accepted_runs.json", data)

    def get_baseline(self, doc_id: str) -> str | None:
        """Get the baseline run ID for a document."""
        data = self._load_state("baselines.json")
        return data.get(doc_id)

    def set_baseline(self, doc_id: str, run_id: str) -> None:
        """Set the baseline run ID for a document."""
        data = self._load_state("baselines.json")
        data[doc_id] = run_id
        self._save_state("baselines.json", data)

    def _load_state(self, filename: str) -> dict[str, Any]:
        """Load state from a JSON file."""
        path = self.state_root / filename
        if not path.exists():
            return {}
        result = read_raw_json(path)
        if not isinstance(result, dict):
            return {}
        return result

    def _save_state(self, filename: str, data: dict[str, Any]) -> None:
        """Save state to a JSON file."""
        write_raw_json(self.state_root / filename, data)
