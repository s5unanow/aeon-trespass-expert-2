"""Tests for QA translation rules."""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import (
    HeadingBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.qa.rules.translation_rules import (
    EmptyTranslationRule,
    MissingTranslationRule,
)


def _page(
    blocks: list[HeadingBlock | ParagraphBlock],
    page_number: int = 1,
    render_mode: str = "semantic",
) -> PageRecord:
    return PageRecord(
        page_number=page_number,
        doc_id="doc",
        width_pt=612,
        height_pt=792,
        render_mode=render_mode,
        blocks=blocks,
    )


class TestMissingTranslationRule:
    def test_flags_missing_ru_text(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello world")],
                ),
            ]
        )
        rule = MissingTranslationRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].rule_id == "translation.missing"
        assert issues[0].severity == "warning"
        assert issues[0].location.page_number == 1

    def test_no_issue_when_translated(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text="Privyet")],
                ),
            ]
        )
        rule = MissingTranslationRule()
        assert rule.check([page], None) == []

    def test_skips_facsimile_pages(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Untranslated")],
                ),
            ],
            render_mode="facsimile",
        )
        rule = MissingTranslationRule()
        assert rule.check([page], None) == []

    def test_skips_whitespace_only_text(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="   ")],
                ),
            ]
        )
        rule = MissingTranslationRule()
        assert rule.check([page], None) == []

    def test_multiple_text_runs(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[
                        TextRun(text="Translated", ru_text="OK"),
                        TextRun(text="Missing"),
                        TextRun(text="Also missing"),
                    ],
                ),
            ]
        )
        rule = MissingTranslationRule()
        issues = rule.check([page], None)
        assert len(issues) == 2


class TestEmptyTranslationRule:
    def test_flags_empty_ru_text(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text="")],
                ),
            ]
        )
        rule = EmptyTranslationRule()
        issues = rule.check([page], None)
        assert len(issues) == 1
        assert issues[0].rule_id == "translation.empty"
        assert issues[0].severity == "error"

    def test_flags_whitespace_ru_text(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text="   ")],
                ),
            ]
        )
        rule = EmptyTranslationRule()
        issues = rule.check([page], None)
        assert len(issues) == 1

    def test_no_issue_when_ru_text_present(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text="Valid")],
                ),
            ]
        )
        rule = EmptyTranslationRule()
        assert rule.check([page], None) == []

    def test_no_issue_when_ru_text_none(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text=None)],
                ),
            ]
        )
        rule = EmptyTranslationRule()
        assert rule.check([page], None) == []

    def test_skips_whitespace_source(self) -> None:
        page = _page(
            [
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="  ", ru_text="")],
                ),
            ]
        )
        rule = EmptyTranslationRule()
        assert rule.check([page], None) == []
