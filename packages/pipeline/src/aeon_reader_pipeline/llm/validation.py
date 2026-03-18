"""LLM response validation and structured output parsing."""

from __future__ import annotations

from typing import Any

import orjson

from aeon_reader_pipeline.models.translation_models import (
    TranslatedNode,
    TranslationResult,
    TranslationUnit,
)


class ValidationError(Exception):
    """Raised when LLM output fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


def _try_repair_json(raw_text: str) -> dict[str, Any] | None:
    """Attempt to salvage truncated JSON by closing open structures."""
    # Try progressively more aggressive repairs
    for suffix in ["]}", '"}]}', '"}]}'[::-1]]:
        try:
            data = orjson.loads((raw_text.rstrip() + suffix).encode("utf-8"))
            if isinstance(data, dict) and "translations" in data:
                return data
        except (orjson.JSONDecodeError, ValueError):
            continue
    return None


def parse_translation_response(  # noqa: C901, PLR0912
    raw_text: str,
    unit: TranslationUnit,
    provider: str = "",
    model: str = "",
    prompt_bundle: str = "",
) -> TranslationResult:
    """Parse and validate an LLM response into a TranslationResult.

    Raises ValidationError if the response is structurally invalid.
    """
    errors: list[str] = []

    # Parse JSON — try repair if truncated
    data: dict[str, Any] | None = None
    try:
        data = orjson.loads(raw_text.encode("utf-8"))
    except (orjson.JSONDecodeError, ValueError):
        data = _try_repair_json(raw_text)
        if data is None:
            raise ValidationError(["Invalid JSON (even after repair attempt)"]) from None

    if not isinstance(data, dict):
        raise ValidationError(["Response is not a JSON object"])

    # Validate unit_id
    resp_unit_id = data.get("unit_id", "")
    if resp_unit_id != unit.unit_id:
        errors.append(f"unit_id mismatch: expected {unit.unit_id}, got {resp_unit_id}")

    # Validate translations array
    translations_raw = data.get("translations")
    if not isinstance(translations_raw, list):
        raise ValidationError(["'translations' field is missing or not an array"])

    # Build source text lookup for fallback
    source_by_id = {n.inline_id: n.source_text for n in unit.text_nodes}
    expected_ids = set(source_by_id.keys())
    seen_ids: set[str] = set()
    translations: list[TranslatedNode] = []

    for entry in translations_raw:
        if not isinstance(entry, dict):
            errors.append(f"Translation entry is not an object: {entry}")
            continue

        inline_id = entry.get("inline_id", "")
        ru_text = entry.get("ru_text", "")

        if not inline_id:
            errors.append("Translation entry missing inline_id")
            continue

        if inline_id not in expected_ids:
            continue  # skip unexpected IDs silently

        if inline_id in seen_ids:
            continue  # skip duplicates silently

        # Fall back to source text when ru_text is empty
        if not ru_text:
            ru_text = source_by_id.get(inline_id, "")

        if not ru_text:
            continue

        seen_ids.add(inline_id)
        translations.append(TranslatedNode(inline_id=inline_id, ru_text=ru_text))

    # Fill in any missing IDs with source text (untranslated fallback)
    missing = expected_ids - seen_ids
    for mid in sorted(missing):
        source = source_by_id.get(mid, "")
        if source:
            translations.append(TranslatedNode(inline_id=mid, ru_text=source))

    if not translations:
        raise ValidationError(["No translations could be extracted"])

    if errors:
        raise ValidationError(errors)

    from aeon_reader_pipeline.utils.ids import content_fingerprint

    result_text = " ".join(t.ru_text for t in translations)
    result_fp = content_fingerprint(result_text)

    return TranslationResult(
        unit_id=unit.unit_id,
        translations=translations,
        provider=provider,
        model=model,
        prompt_bundle=prompt_bundle,
        source_fingerprint=unit.source_fingerprint,
        result_fingerprint=result_fp,
    )


def validate_glossary_compliance(
    result: TranslationResult,
    unit: TranslationUnit,
) -> list[str]:
    """Check that locked glossary terms are used correctly in translation.

    Returns list of warning messages (not hard failures).
    """
    warnings: list[str] = []
    locked_terms = [h for h in unit.glossary_subset if h.locked]
    if not locked_terms:
        return warnings

    all_translated = " ".join(t.ru_text for t in result.translations)

    for hint in locked_terms:
        # Check if the Russian locked term appears in the translation
        if hint.ru.lower() not in all_translated.lower():
            # Only warn if the English source term was in the source
            source_text = " ".join(n.source_text for n in unit.text_nodes)
            if hint.en.lower() in source_text.lower():
                warnings.append(
                    f"Locked term '{hint.en}' -> '{hint.ru}' may not be used in translation"
                )

    return warnings
