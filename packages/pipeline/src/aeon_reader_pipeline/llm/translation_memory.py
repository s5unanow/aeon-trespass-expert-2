"""Translation memory for reusing previously approved translations.

V1: exact-match reuse only — no fuzzy matching.
A unit is a cache hit if and only if its source_fingerprint matches.
"""

from __future__ import annotations

import threading
from pathlib import Path

import structlog

from aeon_reader_pipeline.io.json_io import read_json, write_json
from aeon_reader_pipeline.models.translation_models import (
    TranslationResult,
    TranslationUnit,
)

logger = structlog.get_logger()


def _is_cacheable(unit: TranslationUnit, result: TranslationResult) -> bool:
    """Check whether a translation result is worth caching.

    Rejects results that are empty or consist entirely of untranslated
    source-text fallbacks — caching those would poison future lookups.
    """
    if not result.translations:
        return False

    source_by_id = {n.inline_id: n.source_text for n in unit.text_nodes}

    # Count how many translations actually differ from source text.
    # Only consider nodes whose inline_id exists in the unit — ignore ghosts.
    translated_count = 0
    for node in result.translations:
        source = source_by_id.get(node.inline_id)
        if source is not None and node.ru_text and node.ru_text != source:
            translated_count += 1

    return translated_count > 0


class TranslationMemory:
    """Exact-match translation cache keyed by source fingerprint.

    Thread-safe: all read/write operations are serialized through a lock
    so the TM can be shared across a ThreadPoolExecutor.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def lookup(self, unit: TranslationUnit) -> TranslationResult | None:
        """Look up a cached result by source fingerprint.

        Returns None on cache miss.
        """
        if not unit.source_fingerprint:
            return None

        with self._lock:
            path = self._path_for(unit.source_fingerprint)
            if not path.exists():
                return None

            result = read_json(path, TranslationResult)

        # Mark as cached (outside lock — no I/O)
        return result.model_copy(update={"cached": True})

    def store(self, unit: TranslationUnit, result: TranslationResult) -> None:
        """Store a translation result for future reuse.

        Skips storage if the result has no meaningful translations
        (e.g. all entries are just source-text fallbacks).

        If another thread already wrote for this fingerprint, the write
        is skipped (first-writer-wins).
        """
        if not unit.source_fingerprint:
            return

        if not _is_cacheable(unit, result):
            reason = (
                "empty_translations" if not result.translations else "no_meaningful_translations"
            )
            logger.warning(
                "tm_store_skipped",
                unit_id=unit.unit_id,
                reason=reason,
                translation_count=len(result.translations),
            )
            return

        with self._lock:
            path = self._path_for(unit.source_fingerprint)
            # First-writer-wins: skip if another thread already stored
            if path.exists():
                return
            write_json(path, result)

    def has(self, fingerprint: str) -> bool:
        """Check if a fingerprint exists in the cache."""
        with self._lock:
            return self._path_for(fingerprint).exists()

    def _path_for(self, fingerprint: str) -> Path:
        return self._cache_dir / f"{fingerprint}.json"
