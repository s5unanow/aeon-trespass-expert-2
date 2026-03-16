"""Shared test fixtures for backend tests."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
PDF_FIXTURES_DIR = FIXTURES_DIR / "pdf"
GOLDENS_DIR = Path(__file__).parent / "goldens"

_FONT = "helv"
_FONT_BOLD = "hebo"
_FONT_ITALIC = "heit"


@pytest.fixture(scope="session", autouse=True)
def generate_fixture_pdfs() -> None:
    """Generate synthetic fixture PDFs once per test session."""
    PDF_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    _create_simple_text_pdf()
    _create_multiformat_pdf()
    _create_images_pdf()


def _create_simple_text_pdf() -> None:
    """Simple 2-page PDF with headings and body text."""
    path = PDF_FIXTURES_DIR / "simple_text.pdf"
    if path.exists():
        return
    doc = pymupdf.open()

    # Page 1
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter 1: Introduction", fontsize=18, fontname=_FONT)
    page.insert_text(
        (72, 110),
        "This is the first paragraph of the introduction.",
        fontsize=11,
        fontname=_FONT,
    )
    page.insert_text(
        (72, 135),
        "This is the second paragraph with more detail.",
        fontsize=11,
        fontname=_FONT,
    )

    # Page 2
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter 2: Rules", fontsize=18, fontname=_FONT)
    page.insert_text(
        (72, 110),
        "Rule 1: Players take turns clockwise.",
        fontsize=11,
        fontname=_FONT,
    )
    page.insert_text(
        (72, 135),
        "Rule 2: Each turn consists of three phases.",
        fontsize=11,
        fontname=_FONT,
    )

    toc = [[1, "Chapter 1: Introduction", 1], [1, "Chapter 2: Rules", 2]]
    doc.set_toc(toc)
    doc.set_metadata({"title": "Simple Text Fixture", "author": "Test Suite"})
    doc.save(str(path))
    doc.close()


def _create_multiformat_pdf() -> None:
    """PDF with mixed formatting: bold, italic, different sizes."""
    path = PDF_FIXTURES_DIR / "multiformat.pdf"
    if path.exists():
        return
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    y = 72
    page.insert_text((72, y), "Main Title", fontsize=24, fontname=_FONT_BOLD)
    y += 40
    page.insert_text((72, y), "Subtitle text here", fontsize=14, fontname=_FONT_ITALIC)
    y += 30
    page.insert_text(
        (72, y),
        "Normal paragraph text that continues for a while.",
        fontsize=11,
        fontname=_FONT,
    )
    y += 25
    page.insert_text((72, y), "• First bullet point", fontsize=11, fontname=_FONT)
    y += 20
    page.insert_text((72, y), "• Second bullet point", fontsize=11, fontname=_FONT)
    y += 20
    page.insert_text((72, y), "• Third bullet point", fontsize=11, fontname=_FONT)
    y += 30
    page.insert_text((72, y), "Section Header", fontsize=16, fontname=_FONT_BOLD)
    y += 25
    page.insert_text(
        (72, y),
        "More body text after the section header.",
        fontsize=11,
        fontname=_FONT,
    )

    doc.set_metadata({"title": "Multiformat Fixture"})
    doc.save(str(path))
    doc.close()


def _create_images_pdf() -> None:
    """PDF with embedded images and text."""
    path = PDF_FIXTURES_DIR / "with_images.pdf"
    if path.exists():
        return
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text((72, 72), "Page with Figures", fontsize=16, fontname=_FONT)
    page.insert_text((72, 100), "Below is Figure 1:", fontsize=11, fontname=_FONT)

    # Insert a colored image
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 80), 0)
    pix.set_rect(pymupdf.IRect(0, 0, 50, 80), (200, 50, 50))
    pix.set_rect(pymupdf.IRect(50, 0, 100, 80), (50, 50, 200))
    page.insert_image(pymupdf.Rect(72, 120, 300, 280), pixmap=pix)

    page.insert_text(
        (72, 300),
        "Figure 1: Color diagram",
        fontsize=10,
        fontname=_FONT_ITALIC,
    )
    page.insert_text(
        (72, 330),
        "Continuation of text after the figure.",
        fontsize=11,
        fontname=_FONT,
    )

    # Second image
    pix2 = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), 0)
    pix2.set_rect(pix2.irect, (0, 180, 0))
    page.insert_image(pymupdf.Rect(72, 360, 200, 460), pixmap=pix2)
    page.insert_text(
        (72, 480),
        "Figure 2: Green square",
        fontsize=10,
        fontname=_FONT_ITALIC,
    )

    doc.set_metadata({"title": "Images Fixture"})
    doc.save(str(path))
    doc.close()
