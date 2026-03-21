"""Tests for symbol candidate detection and classification (S5U-258)."""

from __future__ import annotations

from aeon_reader_pipeline.models.config_models import (
    SymbolDetectionConfig,
    SymbolEntry,
    SymbolPack,
)
from aeon_reader_pipeline.models.evidence_models import (
    AssetClass,
    AssetOccurrence,
    DocumentAssetRegistry,
    DocumentSymbolSummary,
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    SymbolCandidate,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.ids import symbol_candidate_id
from aeon_reader_pipeline.utils.symbol_candidates import (
    infer_bbox_anchor,
    infer_text_anchor,
    build_symbol_summary,
    compute_page_symbol_ids,
    generate_page_candidates,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_SMALL_BBOX = NormalizedBBox(x0=0.1, y0=0.1, x1=0.15, y1=0.15)
_MID_BBOX = NormalizedBBox(x0=0.1, y0=0.1, x1=0.3, y1=0.3)


def _make_page(
    *,
    page_number: int = 1,
    text_primitives: list[TextPrimitiveEvidence] | None = None,
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        text_primitives=text_primitives or [],
        image_primitives=image_primitives or [],
        drawing_primitives=drawing_primitives or [],
    )


def _make_registry(
    asset_classes: list[AssetClass] | None = None,
) -> DocumentAssetRegistry:
    classes = asset_classes or []
    total = sum(ac.occurrence_count for ac in classes)
    return DocumentAssetRegistry(
        doc_id="test-doc",
        total_pages_analyzed=1,
        asset_classes=classes,
        total_occurrences=total,
    )


def _make_pack(symbols: list[SymbolEntry] | None = None) -> SymbolPack:
    return SymbolPack(pack_id="test-pack", version="1.0.0", symbols=symbols or [])


def _make_symbol(
    symbol_id: str,
    *,
    text_tokens: list[str] | None = None,
    image_hashes: list[str] | None = None,
    vector_signatures: list[str] | None = None,
) -> SymbolEntry:
    return SymbolEntry(
        symbol_id=symbol_id,
        label_en=symbol_id,
        label_ru=symbol_id,
        detection=SymbolDetectionConfig(
            text_tokens=text_tokens or [],
            image_hashes=image_hashes or [],
            vector_signatures=vector_signatures or [],
        ),
    )


# ---------------------------------------------------------------------------
# Empty / no-op cases
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_primitives(self) -> None:
        page = _make_page()
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        assert result.candidates == []
        assert result.classified_count == 0
        assert result.unclassified_count == 0

    def test_empty_symbol_pack(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Some normal text",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        # No text tokens to match, no dingbats in "Some normal text"
        assert result.classified_count == 0

    def test_no_primitives_at_all(self) -> None:
        page = _make_page()
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        assert len(result.candidates) == 0


# ---------------------------------------------------------------------------
# Text token detection
# ---------------------------------------------------------------------------


class TestTextTokenDetection:
    def test_single_token_match(self) -> None:
        pack = _make_pack([_make_symbol("sword-icon", text_tokens=["SWORD"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Take the SWORD from the chest",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        classified = [c for c in result.candidates if c.is_classified]
        assert len(classified) == 1
        assert classified[0].symbol_id == "sword-icon"
        assert classified[0].evidence_source == "text_token"
        assert classified[0].matched_token == "SWORD"

    def test_multiple_tokens(self) -> None:
        pack = _make_pack(
            [
                _make_symbol("sword-icon", text_tokens=["SWORD"]),
                _make_symbol("shield-icon", text_tokens=["SHIELD"]),
            ]
        )
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="SWORD and SHIELD",
                ),
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        classified = [c for c in result.candidates if c.is_classified]
        assert len(classified) == 2
        ids = {c.symbol_id for c in classified}
        assert ids == {"sword-icon", "shield-icon"}

    def test_token_not_in_text(self) -> None:
        pack = _make_pack([_make_symbol("sword-icon", text_tokens=["SWORD"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Just some text",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        assert result.classified_count == 0

    def test_case_sensitive(self) -> None:
        pack = _make_pack([_make_symbol("sword-icon", text_tokens=["SWORD"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Take the sword",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        # "sword" != "SWORD" — case sensitive
        text_token_cands = [c for c in result.candidates if c.evidence_source == "text_token"]
        assert len(text_token_cands) == 0


# ---------------------------------------------------------------------------
# Raster hash detection
# ---------------------------------------------------------------------------


class TestRasterHashDetection:
    def test_content_hash_match(self) -> None:
        pack = _make_pack([_make_symbol("fire-icon", image_hashes=["abc123"])])
        registry = _make_registry(
            [
                AssetClass(
                    asset_class_id="asset:raster:000",
                    kind="raster",
                    content_hash="abc123",
                    occurrence_count=1,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:000:p0001:00",
                            page_number=1,
                            bbox_norm=_SMALL_BBOX,
                            source_primitive_id="image:p0001:000",
                        )
                    ],
                )
            ]
        )
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="abc123",
                    width_px=32,
                    height_px=32,
                )
            ]
        )
        result = generate_page_candidates(page, registry, pack)
        classified = [c for c in result.candidates if c.evidence_source == "raster_hash"]
        assert len(classified) == 1
        assert classified[0].symbol_id == "fire-icon"
        assert classified[0].is_classified is True
        assert classified[0].matched_hash == "abc123"
        assert classified[0].source_asset_class_id == "asset:raster:000"

    def test_no_match(self) -> None:
        pack = _make_pack([_make_symbol("fire-icon", image_hashes=["abc123"])])
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="xyz999",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        raster_cands = [c for c in result.candidates if c.evidence_source == "raster_hash"]
        assert len(raster_cands) == 0


# ---------------------------------------------------------------------------
# Vector signature detection
# ---------------------------------------------------------------------------


class TestVectorSignatureDetection:
    def test_fingerprint_match(self) -> None:
        # drawing_fingerprint produces "vec:{path_count}:{w}:{h}"
        # For a drawing with path_count=5, bbox 0.1-0.15 x 0.1-0.15:
        # w=0.05, h=0.05 → "vec:5:0.05:0.05"
        pack = _make_pack([_make_symbol("star-icon", vector_signatures=["vec:5:0.05:0.05"])])
        page = _make_page(
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    path_count=5,
                    is_decorative=False,
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        vec_cands = [c for c in result.candidates if c.evidence_source == "vector_signature"]
        assert len(vec_cands) == 1
        assert vec_cands[0].symbol_id == "star-icon"
        assert vec_cands[0].matched_signature == "vec:5:0.05:0.05"

    def test_decorative_skipped(self) -> None:
        pack = _make_pack([_make_symbol("star-icon", vector_signatures=["vec:5:0.05:0.05"])])
        page = _make_page(
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    path_count=5,
                    is_decorative=True,
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        vec_cands = [c for c in result.candidates if c.evidence_source == "vector_signature"]
        assert len(vec_cands) == 0

    def test_no_match(self) -> None:
        pack = _make_pack([_make_symbol("star-icon", vector_signatures=["vec:99:0.5:0.5"])])
        page = _make_page(
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    path_count=5,
                    is_decorative=False,
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        vec_cands = [c for c in result.candidates if c.evidence_source == "vector_signature"]
        assert len(vec_cands) == 0


# ---------------------------------------------------------------------------
# Dingbat detection
# ---------------------------------------------------------------------------


class TestDingbatDetection:
    def test_dingbat_character(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="\u2694",  # CROSSED SWORDS
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        assert len(dingbats) == 1
        assert dingbats[0].codepoint == "\u2694"
        assert dingbats[0].is_classified is False
        assert dingbats[0].codepoint_name == "CROSSED SWORDS"

    def test_normal_text_ignored(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Hello world",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        assert len(dingbats) == 0

    def test_private_use_area(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="\ue000",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        assert len(dingbats) == 1
        assert dingbats[0].codepoint == "\ue000"

    def test_codepoint_name_populated(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="\u2600",  # BLACK SUN WITH RAYS
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        assert len(dingbats) == 1
        assert dingbats[0].codepoint_name == "BLACK SUN WITH RAYS"

    def test_duplicate_dingbats_deduped(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="\u2694\u2694\u2694",  # same char repeated
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        # Same primitive_id + same char → deduplicated to 1
        assert len(dingbats) == 1


# ---------------------------------------------------------------------------
# Confidence values
# ---------------------------------------------------------------------------


class TestConfidenceValues:
    def test_text_token_confidence(self) -> None:
        pack = _make_pack([_make_symbol("s", text_tokens=["X"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(primitive_id="t:p0001:000", bbox_norm=_SMALL_BBOX, text="X")
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        assert result.candidates[0].confidence == 0.95

    def test_raster_hash_confidence(self) -> None:
        pack = _make_pack([_make_symbol("s", image_hashes=["h1"])])
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="i:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="h1",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        raster_cands = [c for c in result.candidates if c.evidence_source == "raster_hash"]
        assert raster_cands[0].confidence == 0.99

    def test_vector_signature_confidence(self) -> None:
        pack = _make_pack([_make_symbol("s", vector_signatures=["vec:5:0.05:0.05"])])
        page = _make_page(
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="d:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    path_count=5,
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        vec_cands = [c for c in result.candidates if c.evidence_source == "vector_signature"]
        assert vec_cands[0].confidence == 0.90

    def test_dingbat_confidence(self) -> None:
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="t:p0001:000", bbox_norm=_SMALL_BBOX, text="\u2694"
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        assert result.candidates[0].confidence == 0.50


# ---------------------------------------------------------------------------
# ID generation
# ---------------------------------------------------------------------------


class TestIdGeneration:
    def test_deterministic_ids(self) -> None:
        pack = _make_pack([_make_symbol("s", text_tokens=["X"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(primitive_id="t:p0001:000", bbox_norm=_SMALL_BBOX, text="X")
            ]
        )
        r1 = generate_page_candidates(page, _make_registry(), pack)
        r2 = generate_page_candidates(page, _make_registry(), pack)
        assert r1.candidates[0].candidate_id == r2.candidates[0].candidate_id

    def test_id_format(self) -> None:
        assert symbol_candidate_id(1, 0) == "sym:p0001:000"
        assert symbol_candidate_id(42, 12) == "sym:p0042:012"

    def test_candidates_get_ids(self) -> None:
        pack = _make_pack([_make_symbol("s", text_tokens=["X"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(primitive_id="t:p0001:000", bbox_norm=_SMALL_BBOX, text="X")
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        assert result.candidates[0].candidate_id == "sym:p0001:000"


# ---------------------------------------------------------------------------
# Document summary
# ---------------------------------------------------------------------------


class TestDocumentSummary:
    def test_summary_aggregation(self) -> None:
        pack = _make_pack(
            [
                _make_symbol("sword", text_tokens=["SWORD"]),
            ]
        )
        page1 = _make_page(
            page_number=1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="t:p0001:000", bbox_norm=_SMALL_BBOX, text="SWORD"
                )
            ],
        )
        page2 = _make_page(
            page_number=2,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="t:p0002:000",
                    bbox_norm=_SMALL_BBOX,
                    text="no match \u2694",
                )
            ],
        )
        reg = _make_registry()
        cands = [
            generate_page_candidates(page1, reg, pack),
            generate_page_candidates(page2, reg, pack),
        ]
        summary = build_symbol_summary(cands, "test-doc")
        assert summary.total_pages_analyzed == 2
        # page1: 1 text_token (classified), page2: 1 dingbat (unclassified)
        assert summary.total_candidates == 2
        assert summary.classified_count == 1
        assert summary.unclassified_count == 1
        assert summary.symbols_found == ["sword"]

    def test_empty_pages(self) -> None:
        summary = build_symbol_summary([], "test-doc")
        assert summary.total_candidates == 0
        assert summary.classified_count == 0
        assert summary.symbols_found == []


# ---------------------------------------------------------------------------
# compute_page_symbol_ids
# ---------------------------------------------------------------------------


class TestComputePageSymbolIds:
    def test_per_page_ids(self) -> None:
        pack = _make_pack([_make_symbol("s", text_tokens=["X"])])
        page = _make_page(
            page_number=3,
            text_primitives=[
                TextPrimitiveEvidence(primitive_id="t:p0003:000", bbox_norm=_SMALL_BBOX, text="X")
            ],
        )
        cands = [generate_page_candidates(page, _make_registry(), pack)]
        result = compute_page_symbol_ids(cands)
        assert 3 in result
        assert result[3] == ["sym:p0003:000"]


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_candidates_roundtrip(self) -> None:
        cand = SymbolCandidate(
            candidate_id="sym:p0001:000",
            page_number=1,
            evidence_source="text_token",
            bbox_norm=_SMALL_BBOX,
            source_primitive_id="text:p0001:000",
            symbol_id="sword",
            confidence=0.95,
            is_classified=True,
            matched_token="SWORD",
        )
        data = cand.model_dump(mode="json")
        restored = SymbolCandidate.model_validate(data)
        assert restored == cand

    def test_page_candidates_roundtrip(self) -> None:
        page = PageSymbolCandidates(
            page_number=1,
            doc_id="test",
            candidates=[
                SymbolCandidate(
                    candidate_id="sym:p0001:000",
                    page_number=1,
                    evidence_source="raster_hash",
                    bbox_norm=_SMALL_BBOX,
                    symbol_id="fire",
                    confidence=0.99,
                    is_classified=True,
                    matched_hash="abc",
                )
            ],
            classified_count=1,
        )
        data = page.model_dump(mode="json")
        restored = PageSymbolCandidates.model_validate(data)
        assert restored == page

    def test_summary_roundtrip(self) -> None:
        summary = DocumentSymbolSummary(
            doc_id="test",
            total_pages_analyzed=5,
            total_candidates=10,
            classified_count=8,
            unclassified_count=2,
            symbols_found=["a", "b"],
        )
        data = summary.model_dump(mode="json")
        restored = DocumentSymbolSummary.model_validate(data)
        assert restored == summary

    def test_anchor_type_roundtrip(self) -> None:
        cand = SymbolCandidate(
            candidate_id="sym:p0001:000",
            page_number=1,
            evidence_source="text_token",
            bbox_norm=_SMALL_BBOX,
            source_primitive_id="text:p0001:000",
            symbol_id="sword",
            confidence=0.95,
            is_classified=True,
            matched_token="SWORD",
            anchor_type="line_prefix",
        )
        data = cand.model_dump(mode="json")
        restored = SymbolCandidate.model_validate(data)
        assert restored.anchor_type == "line_prefix"


# ---------------------------------------------------------------------------
# Anchor type inference
# ---------------------------------------------------------------------------


class TestAnchorTypeInference:
    def test_text_inline_mid_sentence(self) -> None:
        assert infer_text_anchor("Take the SWORD from the chest", "SWORD") == "inline"

    def test_text_line_prefix_at_start(self) -> None:
        assert infer_text_anchor("SWORD Attack +2", "SWORD") == "line_prefix"

    def test_text_line_prefix_with_leading_space(self) -> None:
        assert infer_text_anchor("  SWORD Attack +2", "SWORD") == "line_prefix"

    def test_text_inline_when_no_space_after(self) -> None:
        # Token at start but immediately followed by non-whitespace
        assert infer_text_anchor("SWORDsmith", "SWORD") == "inline"

    def test_text_line_prefix_token_is_entire_text(self) -> None:
        assert infer_text_anchor("SWORD", "SWORD") == "line_prefix"

    def test_bbox_inline_small(self) -> None:
        small = NormalizedBBox(x0=0.1, y0=0.1, x1=0.14, y1=0.14)
        assert infer_bbox_anchor(small) == "inline"

    def test_bbox_block_attached_large(self) -> None:
        large = NormalizedBBox(x0=0.1, y0=0.1, x1=0.3, y1=0.3)
        assert infer_bbox_anchor(large) == "block_attached"

    def test_bbox_inline_boundary(self) -> None:
        # Exactly at the 5% boundary — width=0.05, height=0.04 → still inline
        edge = NormalizedBBox(x0=0.0, y0=0.0, x1=0.049, y1=0.04)
        assert infer_bbox_anchor(edge) == "inline"

    def test_bbox_block_attached_one_axis_large(self) -> None:
        # Width > 5%, height < 5% → block_attached (either axis exceeds)
        wide = NormalizedBBox(x0=0.0, y0=0.0, x1=0.1, y1=0.03)
        assert infer_bbox_anchor(wide) == "block_attached"

    def test_text_token_gets_anchor_type(self) -> None:
        """Integration: text token at line start gets line_prefix."""
        pack = _make_pack([_make_symbol("sword-icon", text_tokens=["SWORD"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="SWORD Attack +2",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        classified = [c for c in result.candidates if c.is_classified]
        assert len(classified) == 1
        assert classified[0].anchor_type == "line_prefix"

    def test_text_token_inline_mid_sentence(self) -> None:
        """Integration: text token mid-sentence gets inline."""
        pack = _make_pack([_make_symbol("sword-icon", text_tokens=["SWORD"])])
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Use your SWORD wisely",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        classified = [c for c in result.candidates if c.is_classified]
        assert len(classified) == 1
        assert classified[0].anchor_type == "inline"

    def test_raster_small_gets_inline(self) -> None:
        """Integration: small raster symbol gets inline anchor."""
        pack = _make_pack([_make_symbol("fire-icon", image_hashes=["abc123"])])
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="abc123",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        raster = [c for c in result.candidates if c.evidence_source == "raster_hash"]
        assert raster[0].anchor_type == "inline"

    def test_raster_large_gets_block_attached(self) -> None:
        """Integration: large raster symbol gets block_attached anchor."""
        large_bbox = NormalizedBBox(x0=0.1, y0=0.1, x1=0.4, y1=0.4)
        pack = _make_pack([_make_symbol("fire-icon", image_hashes=["abc123"])])
        page = _make_page(
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=large_bbox,
                    content_hash="abc123",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), pack)
        raster = [c for c in result.candidates if c.evidence_source == "raster_hash"]
        assert raster[0].anchor_type == "block_attached"

    def test_dingbat_default_inline(self) -> None:
        """Integration: dingbat candidates default to inline."""
        page = _make_page(
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="\u2694",
                )
            ]
        )
        result = generate_page_candidates(page, _make_registry(), _make_pack())
        dingbats = [c for c in result.candidates if c.evidence_source == "text_dingbat"]
        assert dingbats[0].anchor_type == "inline"
