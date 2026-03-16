"""Deterministic hashing for config and artifact identity."""

from __future__ import annotations

import hashlib
from typing import Any

import orjson
from pydantic import BaseModel


def hash_bytes(data: bytes) -> str:
    """SHA-256 hash of raw bytes, returned as hex string."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str) -> str:
    """SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_model(model: BaseModel) -> str:
    """Deterministic SHA-256 hash of a Pydantic model's JSON representation."""
    data = orjson.dumps(
        model.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    )
    return hash_bytes(data)


def hash_dict(data: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of a dict."""
    encoded = orjson.dumps(data, option=orjson.OPT_SORT_KEYS)
    return hash_bytes(encoded)


def hash_string(text: str) -> str:
    """SHA-256 hash of a string."""
    return hash_bytes(text.encode("utf-8"))
