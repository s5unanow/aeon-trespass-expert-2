"""Text normalization utilities for whitespace, unicode, and encoding cleanup."""

from __future__ import annotations

import re
import unicodedata


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization and fix common encoding artifacts."""
    text = unicodedata.normalize("NFC", text)
    # Replace common PDF artifacts
    text = text.replace("\ufb01", "fi")
    text = text.replace("\ufb02", "fl")
    text = text.replace("\u2019", "'")
    text = text.replace("\u201c", '"')
    text = text.replace("\u201d", '"')
    text = text.replace("\u2018", "'")
    text = text.replace("\u00ad", "")  # soft hyphen
    return text


def normalize_text(text: str) -> str:
    """Full text normalization: unicode + whitespace."""
    return normalize_whitespace(normalize_unicode(text))


def strip_bullet(text: str, bullet_patterns: list[str]) -> tuple[str, str]:
    """Strip a leading bullet character from text.

    Returns (bullet, remaining_text). If no bullet found, returns ("", text).
    """
    stripped = text.lstrip()
    for bullet in bullet_patterns:
        if stripped.startswith(bullet):
            rest = stripped[len(bullet) :].lstrip()
            return bullet, rest
    return "", text


def is_likely_heading(
    text: str,
    font_size: float,
    body_font_size: float,
    *,
    min_ratio: float = 1.15,
    max_length: int = 200,
) -> bool:
    """Heuristic: is this text likely a heading based on font size ratio?"""
    if not text.strip():
        return False
    if len(text) > max_length:
        return False
    if body_font_size <= 0:
        return False
    return font_size / body_font_size >= min_ratio


def detect_body_font_size(font_sizes: list[float]) -> float:
    """Find the most common (mode) font size — assumed to be body text."""
    if not font_sizes:
        return 11.0
    from collections import Counter

    counter = Counter(font_sizes)
    return counter.most_common(1)[0][0]
