"""Placeholder injection and restoration for protecting non-translatable tokens."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslatedNode,
)

# Placeholder format: «PH_01», «PH_02», etc.
_PH_PREFIX = "\u00abPH_"
_PH_SUFFIX = "\u00bb"
_PH_PATTERN = re.compile(r"\u00abPH_(\d{2})\u00bb")


class PlaceholderMap(BaseModel):
    """Maps placeholder tokens back to their original locked terms."""

    entries: dict[str, str] = Field(default_factory=dict)


def inject_placeholders(
    text_nodes: list[TextNode],
    glossary_hints: list[GlossaryHint],
) -> tuple[list[TextNode], PlaceholderMap]:
    """Replace locked glossary terms with numbered placeholders.

    Returns modified text nodes and a map to restore originals.
    Only locked terms are replaced.
    """
    locked = [h for h in glossary_hints if h.locked]
    if not locked:
        return text_nodes, PlaceholderMap()

    ph_map: dict[str, str] = {}
    # Build replacement pairs: (en_term, placeholder_token, ru_term)
    replacements: list[tuple[str, str, str]] = []

    for ph_index, hint in enumerate(locked):
        token = f"{_PH_PREFIX}{ph_index:02d}{_PH_SUFFIX}"
        ph_map[token] = hint.ru
        replacements.append((hint.en, token, hint.ru))

    # Sort by length descending to avoid partial matches
    replacements.sort(key=lambda r: len(r[0]), reverse=True)

    new_nodes: list[TextNode] = []
    for node in text_nodes:
        text = node.source_text
        for en_term, placeholder, _ru in replacements:
            text = _case_insensitive_replace(text, en_term, placeholder)
        new_nodes.append(node.model_copy(update={"source_text": text}))

    return new_nodes, PlaceholderMap(entries=ph_map)


def restore_placeholders(
    translations: list[TranslatedNode],
    ph_map: PlaceholderMap,
) -> list[TranslatedNode]:
    """Replace placeholder tokens in translated text with target-language terms."""
    if not ph_map.entries:
        return translations

    result: list[TranslatedNode] = []
    for t in translations:
        text = t.ru_text
        for token, ru_term in ph_map.entries.items():
            text = text.replace(token, ru_term)
        result.append(t.model_copy(update={"ru_text": text}))
    return result


def validate_placeholders(
    translations: list[TranslatedNode],
    ph_map: PlaceholderMap,
) -> list[str]:
    """Check that all placeholders were preserved in the translation.

    Returns a list of error messages for any missing or corrupted placeholders.
    """
    if not ph_map.entries:
        return []

    errors: list[str] = []
    all_text = " ".join(t.ru_text for t in translations)

    for token in ph_map.entries:
        if token not in all_text:
            errors.append(f"Missing placeholder {token} in translation output")

    # Check for unexpected placeholders
    found = _PH_PATTERN.findall(all_text)
    expected_indices = {m.group(1) for m in _PH_PATTERN.finditer(" ".join(ph_map.entries.keys()))}
    for idx in found:
        if idx not in expected_indices:
            errors.append(f"Unexpected placeholder PH_{idx} in translation output")

    return errors


def _case_insensitive_replace(text: str, old: str, new: str) -> str:
    """Replace all case-insensitive occurrences of old with new."""
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    return pattern.sub(new, text)
