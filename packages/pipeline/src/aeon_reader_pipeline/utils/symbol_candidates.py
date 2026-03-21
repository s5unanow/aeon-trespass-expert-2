"""Symbol candidate detection and classification.

Detects symbol candidates from text primitives, raster assets, and vector
clusters, then classifies them against the symbol pack. Pure functions —
no IO or stage dependencies.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict

from aeon_reader_pipeline.models.config_models import SymbolPack
from aeon_reader_pipeline.models.evidence_models import (
    DocumentAssetRegistry,
    DocumentSymbolSummary,
    NormalizedBBox,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    SymbolAnchorType,
    SymbolCandidate,
)
from aeon_reader_pipeline.utils.asset_registry import drawing_fingerprint
from aeon_reader_pipeline.utils.ids import symbol_candidate_id

# ---------------------------------------------------------------------------
# Confidence constants per evidence source
# ---------------------------------------------------------------------------

_CONFIDENCE_RASTER_HASH = 0.99
_CONFIDENCE_TEXT_TOKEN = 0.95
_CONFIDENCE_VECTOR_SIG = 0.90
_CONFIDENCE_DINGBAT = 0.50

# Unicode ranges considered "dingbat-like"
_DINGBAT_RANGES: list[tuple[int, int]] = [
    (0x2500, 0x257F),  # Box Drawing
    (0x2580, 0x259F),  # Block Elements
    (0x25A0, 0x25FF),  # Geometric Shapes
    (0x2600, 0x26FF),  # Miscellaneous Symbols
    (0x2700, 0x27BF),  # Dingbats
    (0x2B50, 0x2B5F),  # Miscellaneous Symbols and Arrows (subset)
    (0xE000, 0xF8FF),  # Private Use Area
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_page_candidates(
    primitive: PrimitivePageEvidence,
    registry: DocumentAssetRegistry,
    symbol_pack: SymbolPack,
) -> PageSymbolCandidates:
    """Generate and classify symbol candidates for a single page.

    Runs four independent detectors (text token, raster hash, vector
    signature, dingbat) and assigns deterministic candidate IDs.

    Note: detectors run independently, so one evidence primitive may
    produce multiple candidates (e.g. a dingbat that also matches a
    text token). This is intentional — classified and unclassified
    candidates are both preserved for downstream review.

    Args:
        primitive: The page's primitive evidence.
        registry: Document-wide asset registry.
        symbol_pack: Canonical symbol pack for classification.

    Returns:
        A PageSymbolCandidates with all detected candidates.
    """
    raw: list[SymbolCandidate] = []
    raw.extend(_detect_text_token_candidates(primitive, symbol_pack))
    raw.extend(_detect_raster_hash_candidates(primitive, registry, symbol_pack))
    raw.extend(_detect_vector_signature_candidates(primitive, registry, symbol_pack))
    raw.extend(_detect_dingbat_candidates(primitive))

    # Assign deterministic IDs
    for idx, cand in enumerate(raw):
        cand = cand.model_copy(
            update={"candidate_id": symbol_candidate_id(primitive.page_number, idx)}
        )
        raw[idx] = cand

    classified = sum(1 for c in raw if c.is_classified)

    return PageSymbolCandidates(
        page_number=primitive.page_number,
        doc_id=primitive.doc_id,
        candidates=raw,
        classified_count=classified,
        unclassified_count=len(raw) - classified,
    )


def build_symbol_summary(
    all_page_candidates: list[PageSymbolCandidates],
    doc_id: str,
) -> DocumentSymbolSummary:
    """Aggregate per-page symbol candidates into a document-level summary."""
    total = 0
    classified = 0
    unclassified = 0
    symbol_ids: set[str] = set()

    for page in all_page_candidates:
        total += len(page.candidates)
        classified += page.classified_count
        unclassified += page.unclassified_count
        for cand in page.candidates:
            if cand.symbol_id:
                symbol_ids.add(cand.symbol_id)

    return DocumentSymbolSummary(
        doc_id=doc_id,
        total_pages_analyzed=len(all_page_candidates),
        total_candidates=total,
        classified_count=classified,
        unclassified_count=unclassified,
        symbols_found=sorted(symbol_ids),
    )


def compute_page_symbol_ids(
    all_page_candidates: list[PageSymbolCandidates],
) -> dict[int, list[str]]:
    """Derive per-page symbol candidate ID lists.

    Returns:
        Dict mapping page_number to list of candidate IDs on that page.
    """
    result: dict[int, list[str]] = defaultdict(list)
    for page in all_page_candidates:
        for cand in page.candidates:
            result[page.page_number].append(cand.candidate_id)
    return dict(result)


# ---------------------------------------------------------------------------
# Anchor-type inference helpers
# ---------------------------------------------------------------------------


def infer_bbox_anchor(bbox: NormalizedBBox) -> SymbolAnchorType:
    """Infer anchor type from a symbol's bounding-box size.

    Small bboxes (< 5% page width and height) are classified as ``inline``.
    Larger bboxes are ``block_attached`` since they likely represent a
    standalone visual element rather than text-level decoration.
    """
    w = bbox.x1 - bbox.x0
    h = bbox.y1 - bbox.y0
    if w < 0.05 and h < 0.05:
        return "inline"
    return "block_attached"


def infer_text_anchor(text: str, token: str) -> SymbolAnchorType:
    """Infer anchor type from a text token's position within its text run.

    Returns ``line_prefix`` when the token appears at the start of the
    stripped text (the symbol leads a line). Otherwise ``inline``.
    """
    stripped = text.lstrip()
    if stripped.startswith(token):
        remaining = stripped[len(token) :]
        # Only count as line_prefix when followed by whitespace or end
        if not remaining or remaining[0] in (" ", "\t", "\n"):
            return "line_prefix"
    return "inline"


# ---------------------------------------------------------------------------
# Internal detectors
# ---------------------------------------------------------------------------


def _detect_text_token_candidates(
    page: PrimitivePageEvidence,
    symbol_pack: SymbolPack,
) -> list[SymbolCandidate]:
    """Match text primitives against symbol pack text_tokens."""
    token_map: dict[str, str] = {}
    for sym in symbol_pack.symbols:
        for token in sym.detection.text_tokens:
            token_map[token] = sym.symbol_id

    if not token_map:
        return []

    candidates: list[SymbolCandidate] = []
    for tp in page.text_primitives:
        for token, sid in token_map.items():
            if token in tp.text:
                anchor: SymbolAnchorType = infer_text_anchor(tp.text, token)
                candidates.append(
                    SymbolCandidate(
                        candidate_id="",  # assigned later
                        page_number=page.page_number,
                        evidence_source="text_token",
                        bbox_norm=tp.bbox_norm,
                        source_primitive_id=tp.primitive_id,
                        symbol_id=sid,
                        confidence=_CONFIDENCE_TEXT_TOKEN,
                        is_classified=True,
                        matched_token=token,
                        anchor_type=anchor,
                    )
                )
    return candidates


def _detect_raster_hash_candidates(
    page: PrimitivePageEvidence,
    registry: DocumentAssetRegistry,
    symbol_pack: SymbolPack,
) -> list[SymbolCandidate]:
    """Match image primitives against symbol pack image_hashes via the registry."""
    hash_map: dict[str, str] = {}
    for sym in symbol_pack.symbols:
        for h in sym.detection.image_hashes:
            hash_map[h] = sym.symbol_id

    if not hash_map:
        return []

    # Build content_hash → asset_class_id lookup from registry
    hash_to_class: dict[str, str] = {}
    for ac in registry.asset_classes:
        if ac.kind == "raster" and ac.content_hash:
            hash_to_class[ac.content_hash] = ac.asset_class_id

    candidates: list[SymbolCandidate] = []
    for img in page.image_primitives:
        if img.content_hash in hash_map:
            anchor = infer_bbox_anchor(img.bbox_norm)
            candidates.append(
                SymbolCandidate(
                    candidate_id="",
                    page_number=page.page_number,
                    evidence_source="raster_hash",
                    bbox_norm=img.bbox_norm,
                    source_primitive_id=img.primitive_id,
                    source_asset_class_id=hash_to_class.get(img.content_hash, ""),
                    symbol_id=hash_map[img.content_hash],
                    confidence=_CONFIDENCE_RASTER_HASH,
                    is_classified=True,
                    matched_hash=img.content_hash,
                    anchor_type=anchor,
                )
            )
    return candidates


def _detect_vector_signature_candidates(
    page: PrimitivePageEvidence,
    registry: DocumentAssetRegistry,
    symbol_pack: SymbolPack,
) -> list[SymbolCandidate]:
    """Match vector drawings against symbol pack vector_signatures."""
    sig_map: dict[str, str] = {}
    for sym in symbol_pack.symbols:
        for sig in sym.detection.vector_signatures:
            sig_map[sig] = sym.symbol_id

    if not sig_map:
        return []

    candidates: list[SymbolCandidate] = []
    for drw in page.drawing_primitives:
        if drw.is_decorative:
            continue
        fp = drawing_fingerprint(drw)
        if fp in sig_map:
            anchor = infer_bbox_anchor(drw.bbox_norm)
            candidates.append(
                SymbolCandidate(
                    candidate_id="",
                    page_number=page.page_number,
                    evidence_source="vector_signature",
                    bbox_norm=drw.bbox_norm,
                    source_primitive_id=drw.primitive_id,
                    symbol_id=sig_map[fp],
                    confidence=_CONFIDENCE_VECTOR_SIG,
                    is_classified=True,
                    matched_signature=fp,
                    anchor_type=anchor,
                )
            )
    return candidates


def _is_dingbat(ch: str) -> bool:
    """Check if a character falls within a dingbat-like Unicode range."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _DINGBAT_RANGES)


def _detect_dingbat_candidates(
    page: PrimitivePageEvidence,
) -> list[SymbolCandidate]:
    """Detect dingbat/symbol-like Unicode characters in text primitives.

    These candidates are always unclassified — they are preserved for
    downstream QA review or manual triage.
    """
    candidates: list[SymbolCandidate] = []
    seen: set[tuple[str, str]] = set()  # (primitive_id, char) dedup

    for tp in page.text_primitives:
        for ch in tp.text:
            if not _is_dingbat(ch):
                continue
            key = (tp.primitive_id, ch)
            if key in seen:
                continue
            seen.add(key)

            cp_name = unicodedata.name(ch, "UNKNOWN")
            candidates.append(
                SymbolCandidate(
                    candidate_id="",
                    page_number=page.page_number,
                    evidence_source="text_dingbat",
                    bbox_norm=tp.bbox_norm,
                    source_primitive_id=tp.primitive_id,
                    codepoint=ch,
                    codepoint_name=cp_name,
                    confidence=_CONFIDENCE_DINGBAT,
                    is_classified=False,
                )
            )
    return candidates
