"""Cross-artifact topology and asset invariant tests.

Validates consistency between DocumentFurnitureProfile, DocumentAssetRegistry,
PageRegionGraph, PageReadingOrder, and CanonicalPageEvidence. These tests catch
contradiction regressions that module-local tests cannot detect.

S5U-310: each test class covers one bug class from the recent topology/asset
review cycle.
"""

from __future__ import annotations

from aeon_reader_pipeline.models.evidence_models import (
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.utils.asset_registry import build_asset_registry
from aeon_reader_pipeline.utils.furniture_detection import (
    compute_page_furniture,
    detect_furniture,
)
from aeon_reader_pipeline.utils.page_region_detection import segment_page_regions
from aeon_reader_pipeline.utils.reading_order import compute_reading_order


def _bbox(x0: float, y0: float, x1: float, y1: float) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _make_page(
    page_number: int,
    *,
    doc_id: str = "test-doc",
    text_primitives: list[TextPrimitiveEvidence] | None = None,
    image_primitives: list[ImagePrimitiveEvidence] | None = None,
    drawing_primitives: list[DrawingPrimitiveEvidence] | None = None,
) -> PrimitivePageEvidence:
    return PrimitivePageEvidence(
        page_number=page_number,
        doc_id=doc_id,
        width_pt=612.0,
        height_pt=792.0,
        text_primitives=text_primitives or [],
        image_primitives=image_primitives or [],
        drawing_primitives=drawing_primitives or [],
    )


# ---------------------------------------------------------------------------
# Invariant 1: Vector furniture cross-referencing
# ---------------------------------------------------------------------------


class TestVectorFurnitureCrossRef:
    """Furniture drawings detected by detect_furniture must be marked
    is_furniture=True in the asset registry built from the same primitives."""

    def test_repeated_divider_marked_in_both_artifacts(self) -> None:
        """A repeated edge divider is furniture AND marked in the asset registry."""
        pages = [
            _make_page(
                i,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id=f"txt:p{i}",
                        bbox_norm=_bbox(0.1, 0.1, 0.9, 0.5),
                        text="Body text",
                    )
                ],
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id=f"drw:p{i}:div",
                        bbox_norm=_bbox(0.05, 0.95, 0.95, 0.97),
                        path_count=3,
                        is_decorative=False,
                    )
                ],
            )
            for i in range(1, 5)
        ]

        furniture_profile = detect_furniture(pages)
        asset_registry = build_asset_registry(pages, furniture_profile)

        # Invariant: every drawing furniture candidate must have a matching
        # is_furniture=True vector asset class
        drawing_furn = [
            c
            for c in furniture_profile.furniture_candidates
            if c.source_primitive_kind == "drawing"
        ]
        assert len(drawing_furn) >= 1, "Divider should be detected as furniture"

        furniture_vectors = [
            ac
            for ac in asset_registry.asset_classes
            if ac.kind == "vector_cluster" and ac.is_furniture
        ]
        assert len(furniture_vectors) >= 1, (
            "At least one vector asset class must be marked is_furniture"
        )

    def test_non_furniture_drawing_not_marked(self) -> None:
        """A drawing that does NOT repeat enough is not furniture in either artifact."""
        pages = [
            _make_page(
                1,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id="txt:p1",
                        bbox_norm=_bbox(0.1, 0.1, 0.9, 0.5),
                        text="Body",
                    )
                ],
                drawing_primitives=[
                    DrawingPrimitiveEvidence(
                        primitive_id="drw:unique",
                        bbox_norm=_bbox(0.3, 0.6, 0.7, 0.8),
                        path_count=5,
                        is_decorative=False,
                    )
                ],
            ),
            _make_page(
                2,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id="txt:p2",
                        bbox_norm=_bbox(0.1, 0.1, 0.9, 0.5),
                        text="Body",
                    )
                ],
            ),
        ]

        furniture_profile = detect_furniture(pages)
        asset_registry = build_asset_registry(pages, furniture_profile)

        # No drawing furniture expected
        drawing_furn = [
            c
            for c in furniture_profile.furniture_candidates
            if c.source_primitive_kind == "drawing"
        ]
        assert len(drawing_furn) == 0

        # No vector classes marked as furniture
        furniture_vectors = [
            ac
            for ac in asset_registry.asset_classes
            if ac.kind == "vector_cluster" and ac.is_furniture
        ]
        assert len(furniture_vectors) == 0


# ---------------------------------------------------------------------------
# Invariant 2: Canonical summary flags match region graph
# ---------------------------------------------------------------------------


class TestCanonicalRegionGraphConsistency:
    """has_figures/has_tables/has_callouts must match region graph contents."""

    def test_furniture_only_images_no_figure_flag(self) -> None:
        """A page whose only images are furniture must not produce figure regions."""
        pages = [
            _make_page(
                i,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id=f"txt:p{i}",
                        bbox_norm=_bbox(0.1, 0.15, 0.9, 0.85),
                        text="Body text content here.",
                    )
                ],
                image_primitives=[
                    ImagePrimitiveEvidence(
                        primitive_id=f"img:p{i}:logo",
                        bbox_norm=_bbox(0.0, 0.01, 0.15, 0.05),
                        content_hash="sha256:logo",
                    )
                ],
            )
            for i in range(1, 5)
        ]

        furniture_profile = detect_furniture(pages)
        page_furn_ids, _, _ = compute_page_furniture(furniture_profile)

        for prim in pages:
            pn = prim.page_number
            furn_ids = page_furn_ids.get(pn, [])
            region_graph = segment_page_regions(prim, furniture_profile, furn_ids)

            # Invariant: region graph has no figure regions
            region_kinds = {r.kind_hint for r in region_graph.regions}
            assert "figure" not in region_kinds, (
                f"Page {pn}: furniture-only images should not produce figure regions"
            )

    def test_content_image_produces_figure_flag(self) -> None:
        """A page with a non-furniture content image must produce figure regions."""
        page = _make_page(
            1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt:body",
                    bbox_norm=_bbox(0.1, 0.1, 0.9, 0.3),
                    text="Body text",
                )
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="img:diagram",
                    bbox_norm=_bbox(0.2, 0.35, 0.8, 0.7),
                    content_hash="sha256:diagram",
                )
            ],
        )
        empty_profile = DocumentFurnitureProfile(doc_id="test-doc", total_pages_analyzed=1)
        region_graph = segment_page_regions(page, empty_profile, [])

        region_kinds = {r.kind_hint for r in region_graph.regions}
        assert "figure" in region_kinds


# ---------------------------------------------------------------------------
# Invariant 3: Interruption tagging correctness
# ---------------------------------------------------------------------------


class TestInterruptionInvariant:
    """Interruption tagging must only apply to true mid-flow breaks."""

    def test_intro_body_pattern_no_false_interruption(self) -> None:
        """single-col intro -> two-col body: intro is NOT an interruption."""
        pages = [
            _make_page(
                1,
                text_primitives=[
                    # Intro heading (full-width)
                    TextPrimitiveEvidence(
                        primitive_id="txt:intro",
                        bbox_norm=_bbox(0.1, 0.05, 0.9, 0.10),
                        text="Chapter Title",
                    ),
                    # Left column
                    TextPrimitiveEvidence(
                        primitive_id="txt:left",
                        bbox_norm=_bbox(0.05, 0.20, 0.45, 0.80),
                        text="Left column text",
                    ),
                    # Right column
                    TextPrimitiveEvidence(
                        primitive_id="txt:right",
                        bbox_norm=_bbox(0.55, 0.20, 0.95, 0.80),
                        text="Right column text",
                    ),
                ],
            )
        ]
        empty_profile = DocumentFurnitureProfile(doc_id="test-doc", total_pages_analyzed=1)
        region_graph = segment_page_regions(pages[0], empty_profile, [])
        reading_order = compute_reading_order(region_graph)

        # Invariant: no reading order entry for the intro band is tagged as interruption
        for entry in reading_order.entries:
            if entry.band_index == 0:
                assert entry.flow_role != "interruption", (
                    "Leading intro band must not be tagged as interruption"
                )

    def test_body_interlude_body_is_interruption(self) -> None:
        """two-col -> single-col -> two-col: middle band IS an interruption."""
        page = _make_page(
            1,
            text_primitives=[
                # Top-left column
                TextPrimitiveEvidence(
                    primitive_id="txt:tl",
                    bbox_norm=_bbox(0.05, 0.05, 0.45, 0.30),
                    text="Top left",
                ),
                # Top-right column
                TextPrimitiveEvidence(
                    primitive_id="txt:tr",
                    bbox_norm=_bbox(0.55, 0.05, 0.95, 0.30),
                    text="Top right",
                ),
                # Full-width interlude
                TextPrimitiveEvidence(
                    primitive_id="txt:interlude",
                    bbox_norm=_bbox(0.1, 0.40, 0.9, 0.45),
                    text="Full-width heading",
                ),
                # Bottom-left column
                TextPrimitiveEvidence(
                    primitive_id="txt:bl",
                    bbox_norm=_bbox(0.05, 0.55, 0.45, 0.80),
                    text="Bottom left",
                ),
                # Bottom-right column
                TextPrimitiveEvidence(
                    primitive_id="txt:br",
                    bbox_norm=_bbox(0.55, 0.55, 0.95, 0.80),
                    text="Bottom right",
                ),
            ],
        )
        empty_profile = DocumentFurnitureProfile(doc_id="test-doc", total_pages_analyzed=1)
        region_graph = segment_page_regions(page, empty_profile, [])
        reading_order = compute_reading_order(region_graph)

        # Find the middle band entry (band_index=1)
        mid_entries = [e for e in reading_order.entries if e.band_index == 1]
        assert len(mid_entries) >= 1
        for entry in mid_entries:
            if entry.kind_hint == "band":
                assert entry.flow_role == "interruption", (
                    "Mid-flow single-col band must be tagged as interruption"
                )


# ---------------------------------------------------------------------------
# Invariant 4: Sidebar/callout producer-consumer alignment
# ---------------------------------------------------------------------------


class TestSidebarCalloutProducerConsumer:
    """The region producer must emit sidebar/callout regions that the reading
    order consumer can actually route as asides."""

    def test_narrow_column_flows_as_aside(self) -> None:
        """A narrow column detected as sidebar must be routed as aside in reading order."""
        page = _make_page(
            1,
            text_primitives=[
                # Wide main column
                TextPrimitiveEvidence(
                    primitive_id="txt:main1",
                    bbox_norm=_bbox(0.05, 0.10, 0.65, 0.15),
                    text="Main body text line 1",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt:main2",
                    bbox_norm=_bbox(0.05, 0.16, 0.65, 0.21),
                    text="Main body text line 2",
                ),
                # Narrow sidebar
                TextPrimitiveEvidence(
                    primitive_id="txt:sidebar",
                    bbox_norm=_bbox(0.75, 0.10, 0.95, 0.15),
                    text="Sidebar note",
                ),
            ],
        )
        empty_profile = DocumentFurnitureProfile(doc_id="test-doc", total_pages_analyzed=1)
        region_graph = segment_page_regions(page, empty_profile, [])
        reading_order = compute_reading_order(region_graph)

        # Producer: sidebar region exists
        sidebars = [r for r in region_graph.regions if r.kind_hint == "sidebar"]
        assert len(sidebars) >= 1, "Producer must emit sidebar region"

        # Consumer: reading order routes it as aside
        sidebar_entries = [e for e in reading_order.entries if e.kind_hint == "sidebar"]
        assert len(sidebar_entries) >= 1, "Consumer must include sidebar entry"
        for entry in sidebar_entries:
            assert entry.flow_role == "aside", "Sidebar must be routed as aside"

    def test_callout_box_flows_as_aside(self) -> None:
        """A drawing-enclosed text detected as callout must be routed as aside."""
        page = _make_page(
            1,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="txt:body",
                    bbox_norm=_bbox(0.1, 0.10, 0.9, 0.15),
                    text="Regular text",
                ),
                TextPrimitiveEvidence(
                    primitive_id="txt:callout",
                    bbox_norm=_bbox(0.15, 0.25, 0.85, 0.30),
                    text="Important callout content",
                ),
            ],
            drawing_primitives=[
                DrawingPrimitiveEvidence(
                    primitive_id="drw:box",
                    bbox_norm=_bbox(0.10, 0.20, 0.90, 0.35),
                    path_count=4,
                    is_decorative=False,
                ),
            ],
        )
        empty_profile = DocumentFurnitureProfile(doc_id="test-doc", total_pages_analyzed=1)
        region_graph = segment_page_regions(page, empty_profile, [])
        reading_order = compute_reading_order(region_graph)

        # Producer: callout region exists
        callouts = [r for r in region_graph.regions if r.kind_hint == "callout"]
        assert len(callouts) >= 1, "Producer must emit callout region"

        # Consumer: reading order routes it as aside
        callout_entries = [e for e in reading_order.entries if e.kind_hint == "callout"]
        assert len(callout_entries) >= 1, "Consumer must include callout entry"
        for entry in callout_entries:
            assert entry.flow_role == "aside", "Callout must be routed as aside"


# ---------------------------------------------------------------------------
# Invariant 5: Asset registry furniture context hints
# ---------------------------------------------------------------------------


class TestFurnitureContextHintConsistency:
    """Furniture-marked asset classes must have context_hint='decoration'."""

    def test_raster_furniture_has_decoration_hint(self) -> None:
        pages = [
            _make_page(
                i,
                text_primitives=[
                    TextPrimitiveEvidence(
                        primitive_id=f"txt:p{i}",
                        bbox_norm=_bbox(0.1, 0.15, 0.9, 0.85),
                        text="Body text",
                    )
                ],
                image_primitives=[
                    ImagePrimitiveEvidence(
                        primitive_id=f"img:p{i}:logo",
                        bbox_norm=_bbox(0.0, 0.01, 0.15, 0.05),
                        content_hash="sha256:logo",
                    )
                ],
            )
            for i in range(1, 5)
        ]
        furniture_profile = detect_furniture(pages)
        asset_registry = build_asset_registry(pages, furniture_profile)

        for ac in asset_registry.asset_classes:
            if ac.is_furniture:
                for occ in ac.occurrences:
                    assert occ.context_hint == "decoration", (
                        f"Furniture asset {ac.asset_class_id} occurrence "
                        f"{occ.occurrence_id} must have context_hint='decoration'"
                    )
