"""Tests for placeholder injection and restoration."""

from __future__ import annotations

from aeon_reader_pipeline.llm.placeholders import (
    PlaceholderMap,
    inject_placeholders,
    restore_placeholders,
    validate_placeholders,
)
from aeon_reader_pipeline.models.translation_models import (
    GlossaryHint,
    TextNode,
    TranslatedNode,
)


class TestPlaceholders:
    def test_no_locked_terms_passes_through(self) -> None:
        nodes = [TextNode(inline_id="i1", source_text="Hello world")]
        hints = [GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=False)]
        result_nodes, ph_map = inject_placeholders(nodes, hints)
        assert result_nodes[0].source_text == "Hello world"
        assert len(ph_map.entries) == 0

    def test_locked_term_replaced(self) -> None:
        nodes = [TextNode(inline_id="i1", source_text="The Titan attacks")]
        hints = [GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True)]
        result_nodes, ph_map = inject_placeholders(nodes, hints)
        assert "Titan" not in result_nodes[0].source_text
        assert "\u00abPH_00\u00bb" in result_nodes[0].source_text
        assert len(ph_map.entries) == 1

    def test_case_insensitive_replacement(self) -> None:
        nodes = [TextNode(inline_id="i1", source_text="The titan is strong")]
        hints = [GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True)]
        result_nodes, _ = inject_placeholders(nodes, hints)
        assert "titan" not in result_nodes[0].source_text.lower()

    def test_multiple_locked_terms(self) -> None:
        nodes = [TextNode(inline_id="i1", source_text="The Titan uses a Shield")]
        hints = [
            GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True),
            GlossaryHint(en="Shield", ru="\u0429\u0438\u0442", locked=True),
        ]
        result_nodes, ph_map = inject_placeholders(nodes, hints)
        assert len(ph_map.entries) == 2
        text = result_nodes[0].source_text
        assert "\u00abPH_00\u00bb" in text
        assert "\u00abPH_01\u00bb" in text

    def test_restore_placeholders(self) -> None:
        ph_map = PlaceholderMap(entries={"\u00abPH_00\u00bb": "\u0422\u0438\u0442\u0430\u043d"})
        translations = [
            TranslatedNode(
                inline_id="i1",
                ru_text="\u00abPH_00\u00bb \u0430\u0442\u0430\u043a\u0443\u0435\u0442",
            ),
        ]
        restored = restore_placeholders(translations, ph_map)
        assert "\u0422\u0438\u0442\u0430\u043d" in restored[0].ru_text
        assert "\u00abPH_" not in restored[0].ru_text

    def test_restore_empty_map_passes_through(self) -> None:
        translations = [
            TranslatedNode(inline_id="i1", ru_text="\u041f\u0440\u0438\u0432\u0435\u0442")
        ]
        restored = restore_placeholders(translations, PlaceholderMap())
        assert restored[0].ru_text == "\u041f\u0440\u0438\u0432\u0435\u0442"

    def test_validate_placeholders_ok(self) -> None:
        ph_map = PlaceholderMap(entries={"\u00abPH_00\u00bb": "\u0422\u0438\u0442\u0430\u043d"})
        translations = [
            TranslatedNode(
                inline_id="i1",
                ru_text="\u00abPH_00\u00bb \u0430\u0442\u0430\u043a\u0443\u0435\u0442",
            ),
        ]
        errors = validate_placeholders(translations, ph_map)
        assert len(errors) == 0

    def test_validate_missing_placeholder(self) -> None:
        ph_map = PlaceholderMap(entries={"\u00abPH_00\u00bb": "\u0422\u0438\u0442\u0430\u043d"})
        translations = [
            TranslatedNode(
                inline_id="i1", ru_text="\u041e\u043d \u0430\u0442\u0430\u043a\u0443\u0435\u0442"
            ),
        ]
        errors = validate_placeholders(translations, ph_map)
        assert len(errors) == 1
        assert "Missing" in errors[0]

    def test_roundtrip_preserves_locked_terms(self) -> None:
        """Full roundtrip: inject -> translate -> validate -> restore."""
        nodes = [TextNode(inline_id="i1", source_text="The Titan attacks the Shield")]
        hints = [
            GlossaryHint(en="Titan", ru="\u0422\u0438\u0442\u0430\u043d", locked=True),
            GlossaryHint(en="Shield", ru="\u0429\u0438\u0442", locked=True),
        ]
        _processed, ph_map = inject_placeholders(nodes, hints)

        # Simulate LLM preserving placeholders
        ru = "\u00abPH_00\u00bb \u0430\u0442\u0430\u043a\u0443\u0435\u0442 \u00abPH_01\u00bb"
        mock_translations = [
            TranslatedNode(inline_id="i1", ru_text=ru),
        ]
        errors = validate_placeholders(mock_translations, ph_map)
        assert len(errors) == 0

        restored = restore_placeholders(mock_translations, ph_map)
        assert "\u0422\u0438\u0442\u0430\u043d" in restored[0].ru_text
        assert "\u0429\u0438\u0442" in restored[0].ru_text
