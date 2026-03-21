"""Symbol evaluation harness — regression gate for symbol detection (S5U-277).

Runs the symbol candidate detection path on curated fixture pages and compares
actual results against expected detections.  CI fails if:

  - An expected semantic symbol is missing
  - An expected symbol's evidence source differs
  - An expected symbol count is too low
  - A forbidden decorative symbol appears as classified

Fixture specs live in ``tests/fixtures/symbol_eval/*.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aeon_reader_pipeline.models.config_models import (
    SymbolDetectionConfig,
    SymbolEntry,
    SymbolPack,
)
from aeon_reader_pipeline.models.evidence_models import (
    AssetClass,
    AssetOccurrence,
    DocumentAssetRegistry,
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PageSymbolCandidates,
    PrimitivePageEvidence,
    SymbolCandidate,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.symbol_candidates import (
    build_symbol_summary,
    generate_page_candidates,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "symbol_eval"

# ---------------------------------------------------------------------------
# Fixture spec model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedDetection:
    symbol_id: str
    evidence_source: str
    count: int


@dataclass(frozen=True)
class SymbolEvalFixture:
    fixture_id: str
    description: str
    expected_semantic: list[ExpectedDetection]
    forbidden_decorative: list[str]


def _load_fixture(name: str) -> SymbolEvalFixture:
    path = _FIXTURE_DIR / f"{name}.json"
    data = json.loads(path.read_text())
    return SymbolEvalFixture(
        fixture_id=data["fixture_id"],
        description=data["description"],
        expected_semantic=[
            ExpectedDetection(
                symbol_id=e["symbol_id"],
                evidence_source=e["evidence_source"],
                count=e["count"],
            )
            for e in data["expected_semantic"]
        ],
        forbidden_decorative=data["forbidden_decorative"],
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SMALL_BBOX = NormalizedBBox(x0=0.1, y0=0.1, x1=0.15, y1=0.15)


def _make_page(
    page_number: int = 1,
    *,
    text_primitives: list[TextPrimitiveEvidence] | None = None,
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id="eval-doc",
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
        doc_id="eval-doc",
        total_pages_analyzed=1,
        asset_classes=classes,
        total_occurrences=total,
    )


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


def _make_pack(symbols: list[SymbolEntry]) -> SymbolPack:
    return SymbolPack(pack_id="eval-pack", version="1.0.0", symbols=symbols)


# ---------------------------------------------------------------------------
# Harness: compare actual candidates against fixture expectations
# ---------------------------------------------------------------------------


def _assert_fixture(
    fixture: SymbolEvalFixture,
    all_candidates: list[PageSymbolCandidates],
) -> None:
    """Validate actual symbol candidates against fixture expectations."""
    # Flatten all classified candidates across pages
    classified: list[SymbolCandidate] = []
    for page_cands in all_candidates:
        classified.extend(c for c in page_cands.candidates if c.is_classified)

    # --- Check expected semantic symbols ---
    for expected in fixture.expected_semantic:
        matches = [
            c
            for c in classified
            if c.symbol_id == expected.symbol_id and c.evidence_source == expected.evidence_source
        ]
        assert len(matches) >= expected.count, (
            f"[{fixture.fixture_id}] Expected at least {expected.count} "
            f"detection(s) of '{expected.symbol_id}' via {expected.evidence_source}, "
            f"got {len(matches)}. "
            f"All classified: {[(c.symbol_id, c.evidence_source) for c in classified]}"
        )

    # --- Check forbidden decorative symbols ---
    for forbidden_id in fixture.forbidden_decorative:
        leaks = [c for c in classified if c.symbol_id == forbidden_id]
        assert len(leaks) == 0, (
            f"[{fixture.fixture_id}] Forbidden decorative symbol '{forbidden_id}' "
            f"leaked as classified with {len(leaks)} detection(s): "
            f"{[(c.evidence_source, c.confidence) for c in leaks]}"
        )


# ---------------------------------------------------------------------------
# Scenario 1: Inline stat/resource icons in body text
# ---------------------------------------------------------------------------


class TestInlineStatIcons:
    """Text token and raster hash detection for inline stat icons."""

    def _build_pages_and_registry(
        self,
    ) -> tuple[list[PrimitivePageEvidence], DocumentAssetRegistry, SymbolPack]:
        pack = _make_pack(
            [
                _make_symbol("sword-icon", text_tokens=["SWORD"]),
                _make_symbol("shield-icon", text_tokens=["SHIELD"]),
                _make_symbol("mana-icon", image_hashes=["hash:mana_blue"]),
            ]
        )

        page1 = _make_page(
            page_number=1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Spend 2 SWORD to attack. Use SHIELD to defend.",
                ),
            ],
        )
        page2 = _make_page(
            page_number=2,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0002:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Gain 1 SWORD when resting.",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0002:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="hash:mana_blue",
                    width_px=24,
                    height_px=24,
                ),
            ],
        )

        registry = _make_registry(
            [
                AssetClass(
                    asset_class_id="asset:raster:000",
                    kind="raster",
                    content_hash="hash:mana_blue",
                    occurrence_count=1,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:000:p0002:00",
                            page_number=2,
                            bbox_norm=_SMALL_BBOX,
                            source_primitive_id="image:p0002:000",
                        )
                    ],
                )
            ]
        )
        return [page1, page2], registry, pack

    def test_expected_detections(self) -> None:
        fixture = _load_fixture("inline_stat_icons")
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        _assert_fixture(fixture, results)

    def test_summary_reflects_all_symbols(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        summary = build_symbol_summary(results, "eval-doc")
        assert set(summary.symbols_found) == {"sword-icon", "shield-icon", "mana-icon"}
        assert summary.classified_count >= 4  # 2 sword + 1 shield + 1 mana


# ---------------------------------------------------------------------------
# Scenario 2: Decorative board-tile/art assets (must NOT be semantic)
# ---------------------------------------------------------------------------


class TestDecorativeAssets:
    """Decorative rasters and vectors must not leak as classified symbols."""

    def _build_pages_and_registry(
        self,
    ) -> tuple[list[PrimitivePageEvidence], DocumentAssetRegistry, SymbolPack]:
        # Pack includes decorative asset hashes/signatures that should NOT match
        # any real symbol — the pack only has semantic symbols
        pack = _make_pack(
            [
                _make_symbol("sword-icon", text_tokens=["SWORD"]),
                # Intentionally NOT registering border-ornament or tile-bg
                # as symbols — they should never appear as classified
            ]
        )

        # Page with decorative raster (repeated logo) and decorative vector (border)
        page = _make_page(
            page_number=1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.1, y0=0.15, x1=0.9, y1=0.85),
                    text="Body text with no symbol tokens.",
                ),
            ],
            image_primitives=[
                # Decorative tile background
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                    content_hash="hash:tile_bg_pattern",
                    width_px=800,
                    height_px=600,
                ),
                # Decorative board art
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:001",
                    bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=0.08, y1=0.08),
                    content_hash="hash:board_corner_art",
                    width_px=64,
                    height_px=64,
                ),
            ],
            drawing_primitives=[
                # Decorative border ornament (marked decorative)
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.02, y0=0.02, x1=0.98, y1=0.98),
                    path_count=12,
                    is_decorative=True,
                ),
            ],
        )

        registry = _make_registry(
            [
                AssetClass(
                    asset_class_id="asset:raster:000",
                    kind="raster",
                    content_hash="hash:tile_bg_pattern",
                    occurrence_count=1,
                    is_furniture=True,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:000:p0001:00",
                            page_number=1,
                            bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                            source_primitive_id="image:p0001:000",
                            context_hint="decoration",
                        )
                    ],
                ),
                AssetClass(
                    asset_class_id="asset:raster:001",
                    kind="raster",
                    content_hash="hash:board_corner_art",
                    occurrence_count=1,
                    is_furniture=True,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:001:p0001:00",
                            page_number=1,
                            bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=0.08, y1=0.08),
                            source_primitive_id="image:p0001:001",
                            context_hint="decoration",
                        )
                    ],
                ),
            ]
        )
        return [page], registry, pack

    def test_no_decorative_leakage(self) -> None:
        fixture = _load_fixture("decorative_assets")
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        _assert_fixture(fixture, results)

    def test_zero_classified_on_decorative_page(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        for page_cands in results:
            assert page_cands.classified_count == 0, (
                f"Page {page_cands.page_number}: expected 0 classified candidates "
                f"on decorative-only page, got {page_cands.classified_count}"
            )

    def test_decorative_vector_skipped(self) -> None:
        """Drawings marked is_decorative=True must not produce vector candidates."""
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        for page_cands in results:
            vec_classified = [
                c
                for c in page_cands.candidates
                if c.evidence_source == "vector_signature" and c.is_classified
            ]
            assert len(vec_classified) == 0


# ---------------------------------------------------------------------------
# Scenario 3: Dense icon page with multiple symbol types
# ---------------------------------------------------------------------------


class TestDenseMixedIcons:
    """Dense page exercising all four detection paths simultaneously."""

    def _build_pages_and_registry(
        self,
    ) -> tuple[list[PrimitivePageEvidence], DocumentAssetRegistry, SymbolPack]:
        pack = _make_pack(
            [
                _make_symbol("sword-icon", text_tokens=["SWORD"]),
                _make_symbol("fire-icon", image_hashes=["hash:fire_raster"]),
                _make_symbol("star-icon", vector_signatures=["vec:5:0.05:0.05"]),
                # border-ornament NOT in pack — must not be classified
            ]
        )

        page = _make_page(
            page_number=1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    text="Use SWORD to attack the creature.",
                ),
                # Dingbat character (unclassified)
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:001",
                    bbox_norm=NormalizedBBox(x0=0.5, y0=0.1, x1=0.55, y1=0.15),
                    text="\u2694",  # CROSSED SWORDS dingbat
                ),
            ],
            image_primitives=[
                # Semantic fire icon
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    content_hash="hash:fire_raster",
                    width_px=32,
                    height_px=32,
                ),
                # Decorative tile (not in pack — should not classify)
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:001",
                    bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                    content_hash="hash:tile_bg",
                    width_px=800,
                    height_px=600,
                ),
            ],
            drawing_primitives=[
                # Semantic star vector
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:000",
                    bbox_norm=_SMALL_BBOX,
                    path_count=5,
                    is_decorative=False,
                ),
                # Decorative border (should be skipped)
                DrawingPrimitiveEvidence(
                    primitive_id="drawing:p0001:001",
                    bbox_norm=NormalizedBBox(x0=0.01, y0=0.01, x1=0.99, y1=0.99),
                    path_count=20,
                    is_decorative=True,
                ),
            ],
        )

        registry = _make_registry(
            [
                AssetClass(
                    asset_class_id="asset:raster:000",
                    kind="raster",
                    content_hash="hash:fire_raster",
                    occurrence_count=1,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:000:p0001:00",
                            page_number=1,
                            bbox_norm=_SMALL_BBOX,
                            source_primitive_id="image:p0001:000",
                        )
                    ],
                ),
                AssetClass(
                    asset_class_id="asset:raster:001",
                    kind="raster",
                    content_hash="hash:tile_bg",
                    occurrence_count=1,
                    is_furniture=True,
                    occurrences=[
                        AssetOccurrence(
                            occurrence_id="asset:raster:001:p0001:00",
                            page_number=1,
                            bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
                            source_primitive_id="image:p0001:001",
                            context_hint="decoration",
                        )
                    ],
                ),
            ]
        )
        return [page], registry, pack

    def test_expected_detections(self) -> None:
        fixture = _load_fixture("dense_mixed_icons")
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        _assert_fixture(fixture, results)

    def test_all_evidence_sources_present(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        all_sources = {c.evidence_source for pc in results for c in pc.candidates}
        assert "text_token" in all_sources
        assert "raster_hash" in all_sources
        assert "vector_signature" in all_sources
        assert "text_dingbat" in all_sources

    def test_classified_vs_unclassified_counts(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        # Expected: 3 classified (sword text, fire raster, star vector)
        # At least 1 unclassified (dingbat)
        total_classified = sum(pc.classified_count for pc in results)
        total_unclassified = sum(pc.unclassified_count for pc in results)
        assert total_classified == 3
        assert total_unclassified >= 1

    def test_dingbat_stays_unclassified(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        dingbats = [
            c for pc in results for c in pc.candidates if c.evidence_source == "text_dingbat"
        ]
        for d in dingbats:
            assert not d.is_classified, f"Dingbat candidate {d.candidate_id} must not be classified"

    def test_decorative_border_not_classified(self) -> None:
        """The decorative border drawing must not appear as a classified candidate."""
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        for pc in results:
            for c in pc.candidates:
                if c.source_primitive_id == "drawing:p0001:001":
                    assert not c.is_classified, "Decorative border drawing must not be classified"

    def test_summary_aggregation(self) -> None:
        pages, registry, pack = self._build_pages_and_registry()
        results = [generate_page_candidates(p, registry, pack) for p in pages]
        summary = build_symbol_summary(results, "eval-doc")
        assert set(summary.symbols_found) == {"sword-icon", "fire-icon", "star-icon"}
