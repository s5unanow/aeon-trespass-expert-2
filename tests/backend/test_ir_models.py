"""Tests for canonical IR models."""

from __future__ import annotations

from aeon_reader_pipeline.models.ir_models import (
    Block,
    CaptionBlock,
    DividerBlock,
    FigureBlock,
    HeadingBlock,
    InlineNode,
    ListBlock,
    ListItemBlock,
    PageAnchor,
    PageRecord,
    ParagraphBlock,
    SymbolRef,
    TextRun,
)


class TestInlineNodes:
    def test_text_run_default(self):
        node = TextRun(text="hello")
        assert node.kind == "text"
        assert not node.bold

    def test_symbol_ref(self):
        node = SymbolRef(symbol_id="sword-icon", alt_text="Sword")
        assert node.kind == "symbol"

    def test_discriminated_union_text(self):
        data = {"kind": "text", "text": "hello"}
        from pydantic import TypeAdapter

        ta = TypeAdapter(InlineNode)
        node = ta.validate_python(data)
        assert isinstance(node, TextRun)

    def test_discriminated_union_symbol(self):
        data = {"kind": "symbol", "symbol_id": "shield"}
        from pydantic import TypeAdapter

        ta = TypeAdapter(InlineNode)
        node = ta.validate_python(data)
        assert isinstance(node, SymbolRef)


class TestBlocks:
    def test_heading_block(self):
        b = HeadingBlock(block_id="doc:p0001:b000:heading", level=1)
        assert b.kind == "heading"

    def test_paragraph_block(self):
        b = ParagraphBlock(
            block_id="doc:p0001:b001:paragraph",
            content=[TextRun(text="Hello world")],
        )
        assert b.kind == "paragraph"
        assert len(b.content) == 1

    def test_list_block(self):
        items = [
            ListItemBlock(block_id="li0", bullet="•", content=[TextRun(text="First")]),
            ListItemBlock(block_id="li1", bullet="•", content=[TextRun(text="Second")]),
        ]
        b = ListBlock(block_id="list0", items=items)
        assert b.kind == "list"
        assert len(b.items) == 2

    def test_figure_block(self):
        b = FigureBlock(block_id="fig0", asset_ref="abc123.png")
        assert b.kind == "figure"

    def test_discriminated_union_roundtrip(self):
        from pydantic import TypeAdapter

        ta = TypeAdapter(Block)
        for data in [
            {"kind": "heading", "block_id": "h1", "level": 2},
            {"kind": "paragraph", "block_id": "p1"},
            {"kind": "list", "block_id": "l1"},
            {"kind": "figure", "block_id": "f1"},
            {"kind": "caption", "block_id": "c1"},
            {"kind": "table", "block_id": "t1"},
            {"kind": "callout", "block_id": "co1"},
            {"kind": "divider", "block_id": "d1"},
        ]:
            block = ta.validate_python(data)
            assert block.kind == data["kind"]

    def test_divider_block(self):
        b = DividerBlock(block_id="div0")
        assert b.kind == "divider"

    def test_caption_block(self):
        b = CaptionBlock(
            block_id="cap0",
            content=[TextRun(text="Figure 1: example")],
            parent_block_id="fig0",
        )
        assert b.kind == "caption"


class TestPageRecord:
    def test_page_record_basic(self):
        pr = PageRecord(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            blocks=[
                HeadingBlock(block_id="h1", level=1, content=[TextRun(text="Title")]),
                ParagraphBlock(block_id="p1", content=[TextRun(text="Body text.")]),
            ],
        )
        assert pr.page_number == 1
        assert len(pr.blocks) == 2
        assert pr.render_mode == "semantic"

    def test_page_record_json_roundtrip(self):
        pr = PageRecord(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            blocks=[
                HeadingBlock(block_id="h1", level=1, content=[TextRun(text="Title")]),
                ParagraphBlock(block_id="p1", content=[TextRun(text="Body.")]),
                ListBlock(
                    block_id="l1",
                    items=[ListItemBlock(block_id="li0", content=[TextRun(text="item")])],
                ),
                FigureBlock(block_id="f1", asset_ref="img.png"),
            ],
            anchors=[PageAnchor(anchor_id="a1", block_id="h1", label="Title")],
        )
        data = pr.model_dump(mode="json")
        restored = PageRecord.model_validate(data)
        assert restored.page_number == pr.page_number
        assert len(restored.blocks) == 4
        assert restored.blocks[0].kind == "heading"
        assert restored.blocks[2].kind == "list"

    def test_render_modes(self):
        for mode in ("semantic", "hybrid", "facsimile"):
            pr = PageRecord(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                render_mode=mode,
            )
            assert pr.render_mode == mode
