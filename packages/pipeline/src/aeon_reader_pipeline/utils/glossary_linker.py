"""Glossary term detection and inline link injection.

Scans localized text content for glossary term matches and injects
GlossaryRef nodes. All linking is precomputed here — the frontend
never does runtime glossary detection.
"""

from __future__ import annotations

import re
from typing import Literal

from aeon_reader_pipeline.models.config_models import GlossaryPack, GlossaryTermEntry
from aeon_reader_pipeline.models.ir_models import (
    Block,
    CalloutBlock,
    CaptionBlock,
    GlossaryRef,
    HeadingBlock,
    InlineNode,
    ListBlock,
    ParagraphBlock,
    TextRun,
)

_ContentBlock = HeadingBlock | ParagraphBlock | CaptionBlock | CalloutBlock


class _TermMatcher:
    """Compiled glossary term matcher for a single term."""

    def __init__(self, term: GlossaryTermEntry) -> None:
        self.term = term
        # Build regex matching all surface forms (en + ru variants)
        forms: list[str] = []
        forms.append(re.escape(term.en_canonical))
        forms.extend(re.escape(a) for a in term.en_aliases)
        forms.append(re.escape(term.ru_preferred))
        forms.extend(re.escape(v) for v in term.ru_variants)
        # Sort by length descending so longer forms match first
        forms.sort(key=len, reverse=True)
        pattern_str = "|".join(forms)
        self.pattern = re.compile(f"({pattern_str})", re.IGNORECASE)


def link_glossary_terms(
    blocks: list[Block],
    glossary_pack: GlossaryPack,
    doc_id: str,
) -> list[Block]:
    """Inject GlossaryRef nodes for matched glossary terms.

    Respects each term's link_policy:
    - "always": link every occurrence
    - "first_only": link only the first occurrence per document
    - "never": never link
    """
    applicable = [
        t for t in glossary_pack.terms if _term_applies(t, doc_id) and t.link_policy != "never"
    ]
    if not applicable:
        return blocks

    matchers = [_TermMatcher(t) for t in applicable]
    linked_once: set[str] = set()

    result: list[Block] = []
    for block in blocks:
        if isinstance(block, ListBlock):
            new_items = []
            for item in block.items:
                new_content = _link_in_content(item.content, matchers, linked_once)
                new_items.append(item.model_copy(update={"content": new_content}))
            result.append(block.model_copy(update={"items": new_items}))
        elif isinstance(block, _ContentBlock):
            new_content = _link_in_content(block.content, matchers, linked_once)
            result.append(block.model_copy(update={"content": new_content}))
        else:
            result.append(block)

    return result


def _link_in_content(
    content: list[InlineNode],
    matchers: list[_TermMatcher],
    linked_once: set[str],
) -> list[InlineNode]:
    """Process inline nodes, splitting text runs at glossary matches."""
    result: list[InlineNode] = []
    for node in content:
        if isinstance(node, TextRun):
            result.extend(_split_text_run(node, matchers, linked_once))
        else:
            result.append(node)
    return result


def _split_text_run(  # noqa: C901, PLR0912
    run: TextRun,
    matchers: list[_TermMatcher],
    linked_once: set[str],
) -> list[InlineNode]:
    """Split a text run at glossary term boundaries, inserting GlossaryRef nodes."""
    text = run.text
    if not text.strip():
        return [run]

    # Don't split runs that already have a merged translation — the Russian
    # text covers the full block and splitting would duplicate it.
    if run.ru_text:
        return [run]

    # Find all matches across all matchers
    matches: list[tuple[int, int, GlossaryTermEntry, str]] = []
    for matcher in matchers:
        for m in matcher.pattern.finditer(text):
            matches.append((m.start(), m.end(), matcher.term, m.group()))

    if not matches:
        return [run]

    # Sort by position, then by length descending (longer match wins)
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    # Remove overlapping matches (keep first/longest)
    filtered: list[tuple[int, int, GlossaryTermEntry, str]] = []
    last_end = 0
    for start, end, term, surface in matches:
        if start >= last_end:
            filtered.append((start, end, term, surface))
            last_end = end

    if not filtered:
        return [run]

    result: list[InlineNode] = []
    pos = 0

    for start, end, term, surface in filtered:
        policy: Literal["always", "first_only", "never"] = term.link_policy
        should_link = policy == "always" or (
            policy == "first_only" and term.term_id not in linked_once
        )

        if start > pos:
            result.append(run.model_copy(update={"text": text[pos:start]}))

        if should_link:
            result.append(
                GlossaryRef(
                    term_id=term.term_id,
                    surface_form=surface,
                    ru_surface_form=term.ru_preferred,
                )
            )
            linked_once.add(term.term_id)
        else:
            result.append(run.model_copy(update={"text": surface}))

        pos = end

    if pos < len(text):
        result.append(run.model_copy(update={"text": text[pos:]}))

    return result


def _term_applies(term: GlossaryTermEntry, doc_id: str) -> bool:
    """Check if a glossary term applies to this document."""
    if not term.doc_scope:
        return True
    return "*" in term.doc_scope or doc_id in term.doc_scope
