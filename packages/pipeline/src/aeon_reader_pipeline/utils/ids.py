"""Deterministic ID generation for pages, blocks, and translation units."""

from __future__ import annotations

import hashlib

import orjson
from pydantic import BaseModel


def page_id(doc_id: str, page_number: int) -> str:
    """Generate a readable page ID."""
    return f"{doc_id}:p{page_number:04d}"


def block_id(doc_id: str, page_number: int, block_index: int, kind: str) -> str:
    """Generate a readable block ID."""
    return f"{doc_id}:p{page_number:04d}:b{block_index:03d}:{kind}"


def list_item_id(doc_id: str, page_number: int, block_index: int, item_index: int) -> str:
    """Generate a readable list item ID."""
    return f"{doc_id}:p{page_number:04d}:b{block_index:03d}:li{item_index:02d}"


def anchor_id(doc_id: str, page_number: int, label: str) -> str:
    """Generate a readable anchor ID from a heading label."""
    slug = _slugify(label)
    return f"{doc_id}:p{page_number:04d}:{slug}"


def content_fingerprint(text: str) -> str:
    """SHA-256 fingerprint of text content (first 16 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def model_fingerprint(model: BaseModel) -> str:
    """SHA-256 fingerprint of a Pydantic model (first 16 hex chars)."""
    data = orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(data).hexdigest()[:16]


def page_fingerprint(blocks_text: str, page_number: int) -> str:
    """Fingerprint for a page based on its block content."""
    raw = f"{page_number}:{blocks_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def unit_id(doc_id: str, page_number: int, unit_index: int) -> str:
    """Generate a readable translation unit ID."""
    return f"{doc_id}:u{page_number:04d}_{unit_index:02d}"


def inline_id(block_id_str: str, inline_index: int) -> str:
    """Generate an inline node ID within a block."""
    return f"{block_id_str}:i{inline_index:03d}"


def asset_class_id(kind: str, index: int) -> str:
    """Generate a document-wide asset class ID.

    Format: ``asset:{kind}:{index:03d}``

    Examples: ``asset:raster:000``, ``asset:vector_cluster:003``
    """
    return f"asset:{kind}:{index:03d}"


def asset_occurrence_id(class_id: str, page_number: int, index: int) -> str:
    """Generate an asset occurrence ID on a specific page.

    Format: ``{class_id}:p{page_number:04d}:{index:02d}``

    Examples: ``asset:raster:000:p0001:00``
    """
    return f"{class_id}:p{page_number:04d}:{index:02d}"


def primitive_id(kind: str, page_number: int, index: int) -> str:
    """Generate a stable provenance ID for an extraction primitive.

    Format: ``{kind}:p{page_number:04d}:{index:03d}``

    Examples: ``text:p0001:003``, ``image:p0002:000``, ``table:p0001:001``
    """
    return f"{kind}:p{page_number:04d}:{index:03d}"


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:60] if text else "anchor"
