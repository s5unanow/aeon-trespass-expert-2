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


def strip_decorative_markers(text: str) -> str:
    """Strip PDF decorative markers ({, }, *) used in shadow/outline effects."""
    # Pattern: {Word*Word*Word} or similar decorative wrapping
    if "{" in text and "}" in text:
        text = text.replace("{", " ").replace("}", " ").replace("*", " ")
    return text


def normalize_text(text: str) -> str:
    """Full text normalization: unicode + whitespace + decorative cleanup."""
    text = normalize_unicode(text)
    text = strip_decorative_markers(text)
    return normalize_whitespace(text)


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


def strip_page_number_prefix(text: str) -> str:
    """Strip a leading page number from text like '3 Introduction' or '3Introduction'."""
    m = re.match(r"^(\d{1,3})\s*([A-Z])", text)
    if m:
        return text[m.start(2) :]
    return text


def is_toc_entry(text: str) -> bool:
    """Check if text is a table-of-contents entry with dot leaders."""
    return "...." in text or "\u2026" in text


# Card/reference codes: 2 uppercase letters + 4 digits (e.g. AB0086, AJ0177)
_CARD_CODE_RE = re.compile(r"^[A-Z]{2}\d{4}$")
# Grid coordinates: repeating letter+digit pairs (e.g. A1A2A3A4B1B2B3B4)
_GRID_COORD_RE = re.compile(r"^(?:[A-Za-z]+\d+){3,}$")
# Mangled Roman numerals: 8+ chars of only I, V, X (e.g. IIIIIIVVVIVIIVIIIIX)
_MANGLED_ROMAN_RE = re.compile(r"^[IVXivx]{8,}$")


def is_noise_block(text: str) -> bool:
    """Heuristic: is this text block extraction noise?

    Catches: page numbers, digit fragments, card codes, grid coordinates,
    mangled Roman numerals, garbled text, and truncated fragments.
    """
    stripped = text.strip()
    if not stripped:
        return True

    # Pure digits (page numbers)
    if stripped.isdigit():
        return True

    # Very short fragments (1-2 chars) that aren't single real words
    if len(stripped) <= 2:
        return True

    # Card/reference codes: AB0086, AJ0177, AM0308
    if _CARD_CODE_RE.match(stripped):
        return True

    # Grid coordinates: A1A2A3A4B1B2B3B4
    if _GRID_COORD_RE.match(stripped):
        return True

    # Mangled Roman numerals: IIIIIIVVVIVIIVIIIIX
    if _MANGLED_ROMAN_RE.match(stripped):
        return True

    # High non-alphanumeric ratio (garbled/symbol noise)
    alnum_count = sum(1 for c in stripped if c.isalnum())
    if len(stripped) >= 4 and alnum_count / len(stripped) < 0.5:
        return True

    # Repeating single character: xxxx, NNNN
    return len(stripped) >= 4 and len(set(stripped.lower())) == 1


_MAX_LABEL_WORDS = 6


def is_standalone_label(text: str) -> bool:
    """Heuristic: is this text a standalone label that should not be merged?

    Detects UI labels, section headers, and game terms that appear as
    standalone text blocks: title-case phrases, all-caps terms, and
    single capitalized words (e.g. "Contents", "RHETORIC", "Adventure Tracks").

    Capped at ``_MAX_LABEL_WORDS`` words to avoid matching long title-case
    sentences.
    """
    stripped = text.strip()
    if not stripped or not stripped[0].isalpha():
        return False

    words = stripped.split()
    if len(words) > _MAX_LABEL_WORDS:
        return False

    # All-uppercase text: "IMPRISONMENT", "RHETORIC", "MAP"
    if stripped.isupper():
        return True

    # Single capitalized word: "Contents", "Skills", "Map"
    if len(words) == 1 and stripped[0].isupper():
        return True

    # Title-case phrase: every alphabetic word starts uppercase
    # Handles punctuation like "Boons, Afflictions, Notes"
    alpha_words = [w.strip(",.;:!?") for w in words if w.strip(",.;:!?") and w[0].isalpha()]
    return len(alpha_words) >= 2 and all(w[0].isupper() for w in alpha_words)


def is_likely_heading(
    text: str,
    font_size: float,
    body_font_size: float,
    *,
    min_ratio: float = 1.15,
    max_length: int = 200,
) -> bool:
    """Heuristic: is this text likely a heading based on font size ratio?"""
    stripped = text.strip()
    if not stripped:
        return False
    if len(text) > max_length:
        return False
    if body_font_size <= 0:
        return False
    if stripped.isdigit():
        return False
    if len(stripped) < 3:
        return False
    return font_size / body_font_size >= min_ratio


def detect_body_font_size(font_sizes: list[float]) -> float:
    """Find the most common (mode) font size — assumed to be body text."""
    if not font_sizes:
        return 11.0
    from collections import Counter

    counter = Counter(font_sizes)
    return counter.most_common(1)[0][0]
