"""Tests for text normalization utilities."""

from __future__ import annotations

from aeon_reader_pipeline.utils.normalization import (
    detect_body_font_size,
    is_likely_heading,
    is_noise_block,
    normalize_text,
    normalize_unicode,
    normalize_whitespace,
    strip_bullet,
)


class TestNormalizeWhitespace:
    def test_collapses_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_strips_edges(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_collapses_newlines(self):
        assert normalize_whitespace("hello\n\nworld") == "hello world"

    def test_tabs(self):
        assert normalize_whitespace("hello\t\tworld") == "hello world"


class TestNormalizeUnicode:
    def test_ligatures(self):
        assert normalize_unicode("\ufb01nd") == "find"
        assert normalize_unicode("\ufb02at") == "flat"

    def test_smart_quotes(self):
        result = normalize_unicode("\u201chello\u201d")
        assert result == '"hello"'

    def test_soft_hyphen_removed(self):
        assert normalize_unicode("hel\u00adlo") == "hello"


class TestNormalizeText:
    def test_combined(self):
        result = normalize_text("  \ufb01nd   the \u201ctruth\u201d  ")
        assert result == 'find the "truth"'


class TestStripBullet:
    def test_bullet_stripped(self):
        bullets = ["\u2022", "\u2013", "-", "\u25b6"]
        bullet, text = strip_bullet("\u2022 First item", bullets)
        assert bullet == "\u2022"
        assert text == "First item"

    def test_dash_stripped(self):
        bullets = ["\u2022", "\u2013", "-"]
        bullet, text = strip_bullet("\u2013 Second item", bullets)
        assert bullet == "\u2013"
        assert text == "Second item"

    def test_no_bullet(self):
        bullets = ["\u2022", "\u2013"]
        bullet, text = strip_bullet("Normal text", bullets)
        assert bullet == ""
        assert text == "Normal text"

    def test_leading_whitespace(self):
        bullets = ["•"]
        bullet, text = strip_bullet("  • Item", bullets)
        assert bullet == "•"
        assert text == "Item"


class TestIsLikelyHeading:
    def test_larger_font_is_heading(self):
        assert is_likely_heading("Chapter 1", 18.0, 11.0)

    def test_same_font_not_heading(self):
        assert not is_likely_heading("Normal text", 11.0, 11.0)

    def test_slightly_larger_not_heading(self):
        assert not is_likely_heading("Not heading", 12.0, 11.0, min_ratio=1.15)

    def test_too_long_not_heading(self):
        assert not is_likely_heading("x" * 201, 18.0, 11.0, max_length=200)

    def test_empty_not_heading(self):
        assert not is_likely_heading("", 18.0, 11.0)

    def test_zero_body_size(self):
        assert not is_likely_heading("Title", 18.0, 0.0)


class TestDetectBodyFontSize:
    def test_mode_detection(self):
        sizes = [11.0, 11.0, 11.0, 18.0, 14.0]
        assert detect_body_font_size(sizes) == 11.0

    def test_empty_fallback(self):
        assert detect_body_font_size([]) == 11.0

    def test_single_size(self):
        assert detect_body_font_size([14.0]) == 14.0


class TestIsNoiseBlock:
    """Tests for noise block detection heuristics."""

    # Existing patterns (should still work)
    def test_empty_string(self) -> None:
        assert is_noise_block("") is True

    def test_whitespace_only(self) -> None:
        assert is_noise_block("   ") is True

    def test_pure_digits(self) -> None:
        assert is_noise_block("42") is True
        assert is_noise_block("123") is True

    def test_short_fragments(self) -> None:
        assert is_noise_block("N") is True
        assert is_noise_block("X") is True
        assert is_noise_block("l2") is True

    # New: card/reference codes
    def test_card_codes(self) -> None:
        assert is_noise_block("AB0086") is True
        assert is_noise_block("AJ0177") is True
        assert is_noise_block("AM0308") is True
        assert is_noise_block("AD0121") is True

    # New: grid coordinates
    def test_grid_coordinates(self) -> None:
        assert is_noise_block("A1A2A3A4B1B2B3B4") is True
        assert is_noise_block("Aa1Aa2Aa3Aa4") is True

    # New: mangled Roman numerals
    def test_mangled_roman_numerals(self) -> None:
        assert is_noise_block("IIIIIIVVVIVIIVIIIIX") is True
        assert is_noise_block("IVVVIVIIVIIIIX") is True

    # New: garbled text (high non-alnum ratio)
    def test_garbled_text(self) -> None:
        assert is_noise_block("≈i}+") is True
        assert is_noise_block("≈≈}+{~") is True

    # New: repeating single character
    def test_repeating_character(self) -> None:
        assert is_noise_block("xxxx") is True
        assert is_noise_block("NNNN") is True

    # Should NOT be noise
    def test_real_heading(self) -> None:
        assert is_noise_block("Chapter 1: Introduction") is False

    def test_real_sentence(self) -> None:
        assert is_noise_block("Players take turns clockwise.") is False

    def test_short_real_word(self) -> None:
        assert is_noise_block("Map") is False
        assert is_noise_block("End") is False

    def test_roman_numeral_heading(self) -> None:
        assert is_noise_block("III") is False  # valid Roman numeral (short)

    def test_single_real_word(self) -> None:
        assert is_noise_block("Skills") is False
