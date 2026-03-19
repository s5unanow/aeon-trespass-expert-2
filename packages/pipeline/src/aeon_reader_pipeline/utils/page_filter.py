"""Page range parsing and filtering utilities."""

from __future__ import annotations


def parse_page_range(spec: str) -> list[int]:
    """Parse a page range specification into a sorted list of unique page numbers.

    Supports:
        - Single pages: "15"
        - Ranges: "10-15"
        - Comma-separated: "1,5,8-12"
    """
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s.strip()), int(end_s.strip())
            if start < 1 or end < start:
                raise ValueError(f"Invalid page range: {part}")
            pages.update(range(start, end + 1))
        else:
            page = int(part)
            if page < 1:
                raise ValueError(f"Invalid page number: {page}")
            pages.add(page)

    if not pages:
        raise ValueError(f"Empty page specification: {spec!r}")

    return sorted(pages)


def pages_to_process(page_count: int, page_filter: list[int] | None) -> list[int]:
    """Return the list of 1-indexed page numbers to process.

    If page_filter is None, returns all pages [1..page_count].
    Otherwise returns only filtered pages that are within range.
    """
    if page_filter is None:
        return list(range(1, page_count + 1))

    valid = [p for p in page_filter if 1 <= p <= page_count]
    if not valid:
        raise ValueError(
            f"No valid pages in filter {page_filter} for document with {page_count} pages"
        )
    return valid
