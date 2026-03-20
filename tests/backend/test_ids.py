"""Tests for deterministic ID generation."""

from __future__ import annotations

from aeon_reader_pipeline.utils.ids import (
    anchor_id,
    block_id,
    content_fingerprint,
    list_item_id,
    page_fingerprint,
    page_id,
    primitive_id,
)


class TestPageId:
    def test_format(self):
        assert page_id("my-doc", 1) == "my-doc:p0001"
        assert page_id("my-doc", 42) == "my-doc:p0042"

    def test_zero_padded(self):
        assert page_id("d", 999) == "d:p0999"


class TestBlockId:
    def test_format(self):
        result = block_id("doc", 1, 0, "heading")
        assert result == "doc:p0001:b000:heading"

    def test_paragraph(self):
        result = block_id("doc", 3, 5, "paragraph")
        assert result == "doc:p0003:b005:paragraph"


class TestListItemId:
    def test_format(self):
        result = list_item_id("doc", 1, 2, 0)
        assert result == "doc:p0001:b002:li00"


class TestAnchorId:
    def test_basic(self):
        result = anchor_id("doc", 1, "Chapter 1: Introduction")
        assert result.startswith("doc:p0001:")
        assert "chapter" in result

    def test_special_chars_stripped(self):
        result = anchor_id("doc", 1, "Héllo Wörld!")
        assert ":" in result  # has the page prefix
        # Should not contain non-ascii
        slug_part = result.split(":", 2)[-1]
        assert slug_part.isascii()


class TestContentFingerprint:
    def test_deterministic(self):
        fp1 = content_fingerprint("hello world")
        fp2 = content_fingerprint("hello world")
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_input(self):
        fp1 = content_fingerprint("hello")
        fp2 = content_fingerprint("world")
        assert fp1 != fp2


class TestPrimitiveId:
    def test_text_format(self) -> None:
        assert primitive_id("text", 1, 3) == "text:p0001:003"

    def test_image_format(self) -> None:
        assert primitive_id("image", 2, 0) == "image:p0002:000"

    def test_table_format(self) -> None:
        assert primitive_id("table", 10, 1) == "table:p0010:001"

    def test_drawing_format(self) -> None:
        assert primitive_id("drawing", 1, 0) == "drawing:p0001:000"

    def test_zero_padded(self) -> None:
        assert primitive_id("text", 999, 99) == "text:p0999:099"


class TestPageFingerprint:
    def test_deterministic(self):
        fp1 = page_fingerprint("block text here", 1)
        fp2 = page_fingerprint("block text here", 1)
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_different_page_number(self):
        fp1 = page_fingerprint("same text", 1)
        fp2 = page_fingerprint("same text", 2)
        assert fp1 != fp2
