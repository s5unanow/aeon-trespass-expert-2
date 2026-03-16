"""Tests for LLM response validation."""

from __future__ import annotations

import pytest

from aeon_reader_pipeline.llm.validation import (
    ValidationError,
    parse_translation_response,
    validate_glossary_compliance,
)
from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslationResult,
    TranslationUnit,
)


def _make_unit(
    unit_id: str = "doc:u0001_00",
    text_nodes: list[TextNode] | None = None,
    glossary: list[GlossaryHint] | None = None,
) -> TranslationUnit:
    if text_nodes is None:
        text_nodes = [
            TextNode(inline_id="doc:p0001:b000:heading:i000", source_text="Hello"),
            TextNode(inline_id="doc:p0001:b001:paragraph:i000", source_text="World"),
        ]
    return TranslationUnit(
        unit_id=unit_id,
        doc_id="test-doc",
        page_number=1,
        text_nodes=text_nodes,
        glossary_subset=glossary or [],
        source_fingerprint="abc123",
    )


class TestParseTranslationResponse:
    def test_valid_response(self) -> None:
        raw = (
            '{"unit_id": "doc:u0001_00", "translations": ['
            '{"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "Hi"},'
            '{"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": "World"}'
            "]}"
        )
        unit = _make_unit()
        result = parse_translation_response(raw, unit, provider="test", model="test-model")
        assert result.unit_id == "doc:u0001_00"
        assert len(result.translations) == 2
        assert result.provider == "test"

    def test_invalid_json(self) -> None:
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response("not json", unit)
        assert "Invalid JSON" in str(exc_info.value)

    def test_not_object(self) -> None:
        unit = _make_unit()
        with pytest.raises(ValidationError):
            parse_translation_response("[1, 2, 3]", unit)

    def test_unit_id_mismatch(self) -> None:
        raw = """{
            "unit_id": "wrong_id",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"},
                {"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": "B"}
            ]
        }"""
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "mismatch" in str(exc_info.value)

    def test_missing_translations_field(self) -> None:
        raw = '{"unit_id": "doc:u0001_00"}'
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "not an array" in str(exc_info.value)

    def test_extra_inline_id(self) -> None:
        raw = """{
            "unit_id": "doc:u0001_00",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"},
                {"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": "B"},
                {"inline_id": "extra_id", "ru_text": "C"}
            ]
        }"""
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "Unexpected" in str(exc_info.value)

    def test_missing_inline_id(self) -> None:
        raw = """{
            "unit_id": "doc:u0001_00",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"}
            ]
        }"""
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "Missing" in str(exc_info.value)

    def test_duplicate_inline_id(self) -> None:
        raw = """{
            "unit_id": "doc:u0001_00",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"},
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "B"},
                {"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": "C"}
            ]
        }"""
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "Duplicate" in str(exc_info.value)

    def test_empty_ru_text(self) -> None:
        raw = """{
            "unit_id": "doc:u0001_00",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"},
                {"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": ""}
            ]
        }"""
        unit = _make_unit()
        with pytest.raises(ValidationError) as exc_info:
            parse_translation_response(raw, unit)
        assert "Empty" in str(exc_info.value)

    def test_result_has_fingerprint(self) -> None:
        raw = """{
            "unit_id": "doc:u0001_00",
            "translations": [
                {"inline_id": "doc:p0001:b000:heading:i000", "ru_text": "A"},
                {"inline_id": "doc:p0001:b001:paragraph:i000", "ru_text": "B"}
            ]
        }"""
        unit = _make_unit()
        result = parse_translation_response(raw, unit)
        assert len(result.result_fingerprint) == 16


class TestGlossaryCompliance:
    def test_no_locked_terms(self) -> None:
        result = TranslationResult(
            unit_id="u1",
            translations=[],
        )
        unit = _make_unit()
        warnings = validate_glossary_compliance(result, unit)
        assert len(warnings) == 0

    def test_locked_term_present(self) -> None:
        from aeon_reader_pipeline.models.translation_models import TranslatedNode

        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(
                    inline_id="i1",
                    ru_text="\u0422\u0438\u0442\u0430\u043d",
                )
            ],
        )
        unit = _make_unit(
            text_nodes=[TextNode(inline_id="i1", source_text="Titan attacks")],
            glossary=[GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True)],
        )
        warnings = validate_glossary_compliance(result, unit)
        assert len(warnings) == 0

    def test_locked_term_missing(self) -> None:
        from aeon_reader_pipeline.models.translation_models import TranslatedNode

        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(
                    inline_id="i1",
                    ru_text="\u041e\u043d \u0430\u0442\u0430\u043a\u0443\u0435\u0442",
                )
            ],
        )
        unit = _make_unit(
            text_nodes=[TextNode(inline_id="i1", source_text="Titan attacks")],
            glossary=[GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True)],
        )
        warnings = validate_glossary_compliance(result, unit)
        assert len(warnings) == 1
        assert "Titan" in warnings[0]
