"""Tests for cache key generation."""

from aeon_reader_pipeline.cache.keys import build_cache_key, stage_cache_key


def test_build_cache_key_deterministic():
    key1 = build_cache_key(a="1", b="2")
    key2 = build_cache_key(b="2", a="1")
    assert key1 == key2  # order-independent


def test_build_cache_key_changes_with_value():
    key1 = build_cache_key(a="1")
    key2 = build_cache_key(a="2")
    assert key1 != key2


def test_stage_cache_key():
    key = stage_cache_key(
        stage_name="extract_primitives",
        stage_version="0.1.0",
        pdf_hash="abc123",
        page_number="1",
    )
    assert isinstance(key, str)
    assert len(key) == 64  # SHA-256 hex


def test_stage_cache_key_deterministic():
    key1 = stage_cache_key(stage_name="x", stage_version="1", input="a")
    key2 = stage_cache_key(stage_name="x", stage_version="1", input="a")
    assert key1 == key2
