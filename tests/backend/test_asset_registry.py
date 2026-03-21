"""Tests for cross-page asset registry construction."""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentAssetRegistry,
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    FurnitureCandidate,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
)
from aeon_reader_pipeline.utils.asset_registry import (
    build_asset_registry,
    compute_page_assets,
)


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _make_page(
    page_number: int,
    *,
    doc_id: str = "test-doc",
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id=doc_id,
        width_pt=612.0,
        height_pt=792.0,
        image_primitives=image_primitives or [],
        drawing_primitives=drawing_primitives or [],
    )


def _raster(
    page_number: int, index: int, content_hash: str, bbox: NormalizedBBox
) -> ImagePrimitiveEvidence:
    return ImagePrimitiveEvidence(
        primitive_id=f"image:p{page_number:04d}:{index:03d}",
        bbox_norm=bbox,
        content_hash=content_hash,
        width_px=64,
        height_px=64,
        colorspace="RGB",
    )


def _drawing(
    page_number: int, index: int, path_count: int, bbox: NormalizedBBox
) -> DrawingPrimitiveEvidence:
    return DrawingPrimitiveEvidence(
        primitive_id=f"drawing:p{page_number:04d}:{index:03d}",
        bbox_norm=bbox,
        path_count=path_count,
        is_decorative=False,
    )


class TestEmptyInput:
    def test_empty_primitives(self) -> None:
        registry = build_asset_registry([])
        assert registry.doc_id == ""
        assert registry.total_pages_analyzed == 0
        assert registry.asset_classes == []
        assert registry.total_occurrences == 0

    def test_pages_without_assets(self) -> None:
        pages = [_make_page(i) for i in range(1, 4)]
        registry = build_asset_registry(pages)
        assert registry.total_pages_analyzed == 3
        assert registry.asset_classes == []
        assert registry.total_occurrences == 0


class TestRasterDeduplication:
    def test_same_image_on_multiple_pages(self) -> None:
        """Same content hash across pages produces one asset class."""
        pages = [
            _make_page(
                i,
                image_primitives=[_raster(i, 0, "hash_abc", _bbox(0.1, 0.1, 0.5, 0.5))],
            )
            for i in range(1, 4)
        ]
        registry = build_asset_registry(pages)
        assert len(registry.asset_classes) == 1
        ac = registry.asset_classes[0]
        assert ac.kind == "raster"
        assert ac.content_hash == "hash_abc"
        assert ac.occurrence_count == 3
        assert ac.page_numbers == [1, 2, 3]
        assert len(ac.occurrences) == 3

    def test_different_images_produce_different_classes(self) -> None:
        """Different content hashes produce separate asset classes."""
        pages = [
            _make_page(
                1,
                image_primitives=[
                    _raster(1, 0, "hash_a", _bbox(0.1, 0.1, 0.3, 0.3)),
                    _raster(1, 1, "hash_b", _bbox(0.5, 0.1, 0.8, 0.3)),
                ],
            ),
        ]
        registry = build_asset_registry(pages)
        assert len(registry.asset_classes) == 2
        assert registry.total_occurrences == 2

    def test_same_image_twice_on_same_page(self) -> None:
        """Same hash appearing twice on one page produces two occurrences."""
        pages = [
            _make_page(
                1,
                image_primitives=[
                    _raster(1, 0, "hash_dup", _bbox(0.1, 0.1, 0.2, 0.2)),
                    _raster(1, 1, "hash_dup", _bbox(0.5, 0.5, 0.6, 0.6)),
                ],
            ),
        ]
        registry = build_asset_registry(pages)
        assert len(registry.asset_classes) == 1
        ac = registry.asset_classes[0]
        assert ac.occurrence_count == 2
        assert ac.page_numbers == [1]
        # Occurrence IDs should be distinct
        occ_ids = [o.occurrence_id for o in ac.occurrences]
        assert len(set(occ_ids)) == 2


class TestContextHints:
    def test_small_image_classified_as_inline(self) -> None:
        """A very small image (< 1% page area) is hinted as inline."""
        pages = [
            _make_page(
                1,
                image_primitives=[_raster(1, 0, "tiny", _bbox(0.1, 0.1, 0.15, 0.15))],
            ),
        ]
        registry = build_asset_registry(pages)
        assert registry.asset_classes[0].occurrences[0].context_hint == "inline"

    def test_large_image_classified_as_figure(self) -> None:
        """A large image (>= 4% page area) is hinted as figure."""
        pages = [
            _make_page(
                1,
                image_primitives=[_raster(1, 0, "big", _bbox(0.1, 0.1, 0.6, 0.6))],
            ),
        ]
        registry = build_asset_registry(pages)
        assert registry.asset_classes[0].occurrences[0].context_hint == "figure"


class TestFurnitureMarking:
    def test_furniture_asset_marked(self) -> None:
        """Assets whose content hash matches furniture are marked is_furniture=True."""
        pages = [
            _make_page(
                i,
                image_primitives=[_raster(i, 0, "logo_hash", _bbox(0.0, 0.0, 0.1, 0.05))],
            )
            for i in range(1, 4)
        ]
        profile = DocumentFurnitureProfile(
            doc_id="test-doc",
            total_pages_analyzed=3,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="furn:ornament:000",
                    furniture_type="ornament",
                    bbox_norm=_bbox(0.0, 0.0, 0.1, 0.05),
                    source_primitive_kind="image",
                    page_numbers=[1, 2, 3],
                    repetition_rate=1.0,
                    content_hash="logo_hash",
                ),
            ],
        )
        registry = build_asset_registry(pages, profile)
        assert len(registry.asset_classes) == 1
        ac = registry.asset_classes[0]
        assert ac.is_furniture is True
        for occ in ac.occurrences:
            assert occ.context_hint == "decoration"

    def test_non_furniture_asset_not_marked(self) -> None:
        """Assets not matching furniture hashes are not marked."""
        pages = [
            _make_page(
                1,
                image_primitives=[_raster(1, 0, "content_img", _bbox(0.1, 0.1, 0.5, 0.5))],
            ),
        ]
        profile = DocumentFurnitureProfile(
            doc_id="test-doc",
            total_pages_analyzed=1,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="furn:ornament:000",
                    furniture_type="ornament",
                    bbox_norm=_bbox(0.0, 0.0, 0.1, 0.05),
                    source_primitive_kind="image",
                    page_numbers=[1],
                    repetition_rate=1.0,
                    content_hash="different_hash",
                ),
            ],
        )
        registry = build_asset_registry(pages, profile)
        assert registry.asset_classes[0].is_furniture is False


class TestVectorClusters:
    def test_similar_drawings_grouped(self) -> None:
        """Non-decorative drawings with same path count and dimensions are grouped."""
        pages = [
            _make_page(
                i,
                drawing_primitives=[_drawing(i, 0, 5, _bbox(0.1, 0.1, 0.15, 0.15))],
            )
            for i in range(1, 4)
        ]
        registry = build_asset_registry(pages)
        vc = [ac for ac in registry.asset_classes if ac.kind == "vector_cluster"]
        assert len(vc) == 1
        assert vc[0].occurrence_count == 3
        assert vc[0].path_count == 5

    def test_decorative_drawings_excluded(self) -> None:
        """Decorative drawings are excluded from vector clusters."""
        pages = [
            _make_page(
                i,
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id=f"drawing:p{i:04d}:000",
                        bbox_norm=_bbox(0.0, 0.0, 1.0, 1.0),
                        path_count=20,
                        is_decorative=True,
                    )
                ],
            )
            for i in range(1, 4)
        ]
        registry = build_asset_registry(pages)
        vc = [ac for ac in registry.asset_classes if ac.kind == "vector_cluster"]
        assert len(vc) == 0

    def test_different_drawings_separate_classes(self) -> None:
        """Drawings with different path counts are separate classes."""
        pages = [
            _make_page(
                1,
                drawing_primitives=[
                    _drawing(1, 0, 3, _bbox(0.1, 0.1, 0.15, 0.15)),
                    _drawing(1, 1, 8, _bbox(0.5, 0.1, 0.55, 0.15)),
                ],
            ),
        ]
        registry = build_asset_registry(pages)
        vc = [ac for ac in registry.asset_classes if ac.kind == "vector_cluster"]
        assert len(vc) == 2


class TestComputePageAssets:
    def test_per_page_lookups(self) -> None:
        """compute_page_assets returns correct per-page occurrence IDs."""
        pages = [
            _make_page(
                1,
                image_primitives=[
                    _raster(1, 0, "hash_a", _bbox(0.1, 0.1, 0.5, 0.5)),
                    _raster(1, 1, "hash_b", _bbox(0.6, 0.1, 0.9, 0.3)),
                ],
            ),
            _make_page(
                2,
                image_primitives=[_raster(2, 0, "hash_a", _bbox(0.1, 0.1, 0.5, 0.5))],
            ),
        ]
        registry = build_asset_registry(pages)
        page_assets = compute_page_assets(registry)

        assert 1 in page_assets
        assert len(page_assets[1]) == 2
        assert 2 in page_assets
        assert len(page_assets[2]) == 1

    def test_empty_registry(self) -> None:
        """Empty registry produces empty lookups."""
        registry = DocumentAssetRegistry(doc_id="test", total_pages_analyzed=0)
        assert compute_page_assets(registry) == {}


class TestOccurrenceIds:
    def test_ids_are_deterministic(self) -> None:
        """Running build_asset_registry twice produces the same IDs."""
        pages = [
            _make_page(
                i,
                image_primitives=[_raster(i, 0, "hash_x", _bbox(0.2, 0.2, 0.4, 0.4))],
            )
            for i in range(1, 3)
        ]
        r1 = build_asset_registry(pages)
        r2 = build_asset_registry(pages)
        ids1 = [o.occurrence_id for ac in r1.asset_classes for o in ac.occurrences]
        ids2 = [o.occurrence_id for ac in r2.asset_classes for o in ac.occurrences]
        assert ids1 == ids2

    def test_id_format(self) -> None:
        """Asset IDs follow the expected format."""
        pages = [
            _make_page(
                1,
                image_primitives=[_raster(1, 0, "hash_fmt", _bbox(0.1, 0.1, 0.3, 0.3))],
            ),
        ]
        registry = build_asset_registry(pages)
        ac = registry.asset_classes[0]
        assert ac.asset_class_id == "asset:raster:000"
        assert ac.occurrences[0].occurrence_id == "asset:raster:000:p0001:00"


class TestJsonRoundTrip:
    def test_registry_roundtrip(self) -> None:
        """DocumentAssetRegistry survives JSON round-trip."""
        pages = [
            _make_page(
                i,
                image_primitives=[_raster(i, 0, "hash_rt", _bbox(0.1, 0.1, 0.5, 0.5))],
                drawing_primitives=[_drawing(i, 0, 4, _bbox(0.6, 0.1, 0.65, 0.15))],
            )
            for i in range(1, 3)
        ]
        registry = build_asset_registry(pages)
        payload = registry.model_dump(mode="json")
        restored = DocumentAssetRegistry.model_validate(payload)
        assert restored == registry
