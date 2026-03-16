"""Tests for glossary annotation and linking."""

from __future__ import annotations

from aeon_reader_pipeline.models.config_models import (
    GlossaryPack,
    GlossaryTermEntry,
)
from aeon_reader_pipeline.models.ir_models import (
    GlossaryRef,
    HeadingBlock,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.utils.glossary_linker import link_glossary_terms


def _make_pack(terms: list[GlossaryTermEntry]) -> GlossaryPack:
    return GlossaryPack(pack_id="test", version="1.0.0", terms=terms)


class TestGlossaryLinker:
    def test_no_terms_passes_through(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Hello world")],
            )
        ]
        pack = _make_pack([])
        result = link_glossary_terms(blocks, pack, "doc")
        assert len(result) == 1
        assert result[0].content[0].text == "Hello world"

    def test_links_matching_term(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="The Titan attacks")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        para = result[0]
        assert isinstance(para, ParagraphBlock)
        # Should have: "The " + GlossaryRef + " attacks"
        has_ref = any(isinstance(n, GlossaryRef) for n in para.content)
        assert has_ref

    def test_first_only_links_once(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Titan and Titan")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="first_only",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        para = result[0]
        refs = [n for n in para.content if isinstance(n, GlossaryRef)]
        assert len(refs) == 1

    def test_always_links_all(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Titan and Titan")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        para = result[0]
        refs = [n for n in para.content if isinstance(n, GlossaryRef)]
        assert len(refs) == 2

    def test_never_policy_skips(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="The Titan attacks")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="never",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        para = result[0]
        refs = [n for n in para.content if isinstance(n, GlossaryRef)]
        assert len(refs) == 0

    def test_case_insensitive_match(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="The titan attacks")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        has_ref = any(isinstance(n, GlossaryRef) for n in result[0].content)
        assert has_ref

    def test_russian_variant_match(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[
                    TextRun(
                        text="Hello",
                        ru_text="\u0422\u0438\u0442\u0430\u043d",
                    )
                ],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        # Links against the en text "Hello" — won't match.
        # The linker checks the `text` field, not `ru_text`.
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        refs = [n for n in result[0].content if isinstance(n, GlossaryRef)]
        assert len(refs) == 0

    def test_respects_doc_scope(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="The Titan attacks")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
                doc_scope=["other-doc"],
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        refs = [n for n in result[0].content if isinstance(n, GlossaryRef)]
        assert len(refs) == 0

    def test_links_in_heading(self) -> None:
        blocks = [
            HeadingBlock(
                block_id="h1",
                level=1,
                content=[TextRun(text="The Titan Chapter")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        has_ref = any(isinstance(n, GlossaryRef) for n in result[0].content)
        assert has_ref

    def test_glossary_ref_has_surface_form(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="The Titan attacks")],
            )
        ]
        terms = [
            GlossaryTermEntry(
                term_id="t1",
                en_canonical="Titan",
                ru_preferred="\u0422\u0438\u0442\u0430\u043d",
                link_policy="always",
            ),
        ]
        result = link_glossary_terms(blocks, _make_pack(terms), "doc")
        refs = [n for n in result[0].content if isinstance(n, GlossaryRef)]
        assert len(refs) == 1
        assert refs[0].surface_form == "Titan"
        assert refs[0].term_id == "t1"
