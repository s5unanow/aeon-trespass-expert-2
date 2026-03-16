"""Tests for hashing utilities."""

from aeon_reader_pipeline.config.hashing import hash_bytes, hash_dict, hash_model, hash_string
from aeon_reader_pipeline.models.run_models import PipelineConfig


def test_hash_bytes():
    h = hash_bytes(b"hello")
    assert isinstance(h, str)
    assert len(h) == 64


def test_hash_string():
    h = hash_string("hello")
    assert isinstance(h, str)
    assert len(h) == 64


def test_hash_dict_deterministic():
    h1 = hash_dict({"b": 2, "a": 1})
    h2 = hash_dict({"a": 1, "b": 2})
    assert h1 == h2


def test_hash_model():
    config = PipelineConfig(run_id="test")
    h = hash_model(config)
    assert isinstance(h, str)
    assert len(h) == 64


def test_hash_model_deterministic():
    c1 = PipelineConfig(run_id="test")
    c2 = PipelineConfig(run_id="test")
    assert hash_model(c1) == hash_model(c2)
