"""Translation memory for reusing previously approved translations.

V1: exact-match reuse only — no fuzzy matching.
A unit is a cache hit if and only if its source_fingerprint matches.
"""

from __future__ import annotations

from pathlib import Path

from aeon_reader_pipeline.io.json_io import read_json, write_json
from aeon_reader_pipeline.models.translation_models import (
    TranslationResult,
    TranslationUnit,
)


class TranslationMemory:
    """Exact-match translation cache keyed by source fingerprint."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def lookup(self, unit: TranslationUnit) -> TranslationResult | None:
        """Look up a cached result by source fingerprint.

        Returns None on cache miss.
        """
        if not unit.source_fingerprint:
            return None

        path = self._path_for(unit.source_fingerprint)
        if not path.exists():
            return None

        result = read_json(path, TranslationResult)
        # Mark as cached
        return result.model_copy(update={"cached": True})

    def store(self, unit: TranslationUnit, result: TranslationResult) -> None:
        """Store a translation result for future reuse."""
        if not unit.source_fingerprint:
            return
        path = self._path_for(unit.source_fingerprint)
        write_json(path, result)

    def has(self, fingerprint: str) -> bool:
        """Check if a fingerprint exists in the cache."""
        return self._path_for(fingerprint).exists()

    def _path_for(self, fingerprint: str) -> Path:
        return self._cache_dir / f"{fingerprint}.json"
