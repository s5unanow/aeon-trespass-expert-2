"""Tests for translation models."""

from __future__ import annotations

from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslatedNode,
    TranslationCallMetadata,
    TranslationFailure,
    TranslationPlan,
    TranslationPlanSummary,
    TranslationResult,
    TranslationStageSummary,
    TranslationUnit,
)


class TestTranslationModels:
    def test_translation_unit_roundtrip(self) -> None:
        unit = TranslationUnit(
            unit_id="doc:u0001_00",
            doc_id="test-doc",
            page_number=1,
            block_ids=["doc:p0001:b000:heading"],
            section_path=["Chapter 1"],
            style_hint="heading",
            glossary_subset=[
                GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True)
            ],
            text_nodes=[
                TextNode(inline_id="doc:p0001:b000:heading:i000", source_text="Chapter Title")
            ],
            source_fingerprint="abc123",
        )
        data = unit.model_dump(mode="json")
        restored = TranslationUnit.model_validate(data)
        assert restored.unit_id == unit.unit_id
        assert len(restored.text_nodes) == 1
        assert restored.glossary_subset[0].locked is True

    def test_translation_result_roundtrip(self) -> None:
        result = TranslationResult(
            unit_id="doc:u0001_00",
            translations=[
                TranslatedNode(
                    inline_id="doc:p0001:b000:heading:i000",
                    ru_text="\u0417\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a",
                ),
            ],
            provider="gemini",
            model="gemini-2.0-flash",
            source_fingerprint="abc123",
        )
        data = result.model_dump(mode="json")
        restored = TranslationResult.model_validate(data)
        assert restored.unit_id == result.unit_id
        assert len(restored.translations) == 1

    def test_translation_failure(self) -> None:
        failure = TranslationFailure(
            unit_id="doc:u0001_00",
            error_type="validation_error",
            error_message="Missing inline IDs",
            provider="gemini",
        )
        assert failure.attempt == 1
        assert failure.raw_response == ""

    def test_translation_call_metadata(self) -> None:
        meta = TranslationCallMetadata(
            unit_id="doc:u0001_00",
            provider="gemini",
            model="gemini-2.0-flash",
            prompt_bundle="translate-v1",
            input_tokens=100,
            output_tokens=50,
        )
        assert meta.cache_hit is False

    def test_translation_plan(self) -> None:
        plan = TranslationPlan(
            doc_id="test-doc",
            total_units=2,
            total_text_nodes=5,
        )
        assert len(plan.units) == 0

    def test_plan_summary(self) -> None:
        summary = TranslationPlanSummary(
            doc_id="test-doc",
            page_count=10,
            total_units=20,
            total_text_nodes=80,
            skipped_pages=[5, 6],
        )
        assert len(summary.skipped_pages) == 2

    def test_stage_summary(self) -> None:
        summary = TranslationStageSummary(
            doc_id="test-doc",
            total_units=10,
            completed=8,
            failed=2,
            cached=3,
            status="partial",
        )
        assert summary.status == "partial"

    def test_glossary_hint_defaults(self) -> None:
        hint = GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d")
        assert hint.locked is False

    def test_text_node(self) -> None:
        node = TextNode(inline_id="p0001.b000.i000", source_text="Hello world")
        assert node.source_text == "Hello world"
