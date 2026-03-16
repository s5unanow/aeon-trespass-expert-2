"""Content-addressed cache key builder."""

from __future__ import annotations

from aeon_reader_pipeline.config.hashing import hash_string


def build_cache_key(**components: str) -> str:
    """Build a deterministic cache key from named components.

    All component values are concatenated with separators and hashed.
    Components are sorted by key name for determinism.
    """
    parts = [f"{k}={v}" for k, v in sorted(components.items())]
    combined = "|".join(parts)
    return hash_string(combined)


def stage_cache_key(
    stage_name: str,
    stage_version: str,
    **input_hashes: str,
) -> str:
    """Build a cache key for a stage execution."""
    return build_cache_key(
        stage_name=stage_name,
        stage_version=stage_version,
        **input_hashes,
    )
