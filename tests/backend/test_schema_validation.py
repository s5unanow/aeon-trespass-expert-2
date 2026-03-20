"""Schema-validation test suite for persisted Architecture 3 artifacts.

Validates that every Architecture 3 evidence-layer artifact:
  1. Serializes to JSON that passes the checked-in JSON Schema.
  2. Round-trips through the authoritative Pydantic model.
  3. Rejects payloads with missing required fields or invalid values.

When stages persist artifacts to disk (via ArtifactStore), the on-disk
JSON is also loaded and validated against the schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pymupdf
import pytest

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.models.config_models import (
    DocumentBuild,
    DocumentConfig,
    DocumentProfiles,
    DocumentTitles,
    GlossaryPack,
    ModelProfile,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    DrawingPrimitiveEvidence,
    FontSummary,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PageRasterHandle,
    PrimitivePageEvidence,
    ResolvedPageIR,
    TablePrimitiveEvidence,
    TextPrimitiveEvidence,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.collect_evidence import CollectEvidenceStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.resolve_page_ir import ResolvePageIRStage

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INTERNAL_SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "jsonschema" / "pipeline"

# Models and their corresponding schema filenames
ARCH3_MODELS: list[tuple[str, type[Any]]] = [
    ("PrimitivePageEvidence", PrimitivePageEvidence),
    ("CanonicalPageEvidence", CanonicalPageEvidence),
    ("ResolvedPageIR", ResolvedPageIR),
]


def _load_schema(name: str) -> dict[str, Any]:
    """Load a checked-in JSON Schema by model name."""
    path = INTERNAL_SCHEMA_DIR / f"{name}.json"
    assert path.exists(), f"Schema file missing: {path}"
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _validate_against_schema(instance: dict[str, Any], schema_name: str) -> None:
    """Validate a dict against the checked-in JSON Schema, raising on failure."""
    schema = _load_schema(schema_name)
    jsonschema.validate(instance=instance, schema=schema)


def _make_bbox(**overrides: float) -> NormalizedBBox:
    defaults = {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.2}
    defaults.update(overrides)
    return NormalizedBBox(**defaults)


def _make_primitive_page_evidence(*, rich: bool = False) -> PrimitivePageEvidence:
    """Build a realistic PrimitivePageEvidence fixture.

    Args:
        rich: If True, include all primitive types, raster handle, and font data.
    """
    text_prims = [
        TextPrimitiveEvidence(
            primitive_id="txt-0001",
            bbox_norm=_make_bbox(y0=0.05, y1=0.10),
            text="Chapter Title",
            line_count=1,
            font_name="Helvetica-Bold",
            font_size=20.0,
            is_bold=True,
        ),
        TextPrimitiveEvidence(
            primitive_id="txt-0002",
            bbox_norm=_make_bbox(y0=0.12, y1=0.20),
            text="Body paragraph with some text content.",
            line_count=2,
            font_name="Helvetica",
            font_size=11.0,
        ),
    ]

    image_prims: list[ImagePrimitiveEvidence] = []
    table_prims: list[TablePrimitiveEvidence] = []
    drawing_prims: list[DrawingPrimitiveEvidence] = []
    raster_handle = None
    font_summary = FontSummary()

    if rich:
        image_prims = [
            ImagePrimitiveEvidence(
                primitive_id="img-0001",
                bbox_norm=_make_bbox(y0=0.25, y1=0.55),
                content_hash="sha256:abc123def456",
                width_px=400,
                height_px=300,
                colorspace="RGB",
            ),
        ]
        table_prims = [
            TablePrimitiveEvidence(
                primitive_id="tbl-0001",
                bbox_norm=_make_bbox(y0=0.60, y1=0.80),
                rows=3,
                cols=4,
                cell_count=12,
            ),
        ]
        drawing_prims = [
            DrawingPrimitiveEvidence(
                primitive_id="drw-0001",
                bbox_norm=_make_bbox(y0=0.82, y1=0.85),
                path_count=5,
                is_decorative=True,
            ),
        ]
        raster_handle = PageRasterHandle(
            source_pdf_sha256="sha256:fullhash",
            page_number=1,
            width_pt=612.0,
            height_pt=792.0,
            raster_path="/tmp/raster_p0001.png",
            default_dpi=150,
        )
        font_summary = FontSummary(
            dominant_font="Helvetica",
            dominant_size=11.0,
            unique_font_count=2,
        )

    return PrimitivePageEvidence(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        rotation=0,
        source_pdf_sha256="sha256:testpdfhash",
        text_primitives=text_prims,
        image_primitives=image_prims,
        table_primitives=table_prims,
        drawing_primitives=drawing_prims,
        font_summary=font_summary,
        char_count=52,
        extraction_method="pdfplumber",
        raster_handle=raster_handle,
    )


def _make_canonical_page_evidence(*, with_content: bool = False) -> CanonicalPageEvidence:
    """Build a realistic CanonicalPageEvidence fixture."""
    return CanonicalPageEvidence(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        primitive_evidence_hash="sha256:abc123",
        estimated_column_count=2 if with_content else 1,
        has_tables=with_content,
        has_figures=with_content,
        has_callouts=False,
        furniture_fraction=0.05 if with_content else 0.0,
    )


def _make_resolved_page_ir(
    *,
    render_mode: str = "semantic",
) -> ResolvedPageIR:
    """Build a realistic ResolvedPageIR fixture."""
    return ResolvedPageIR(
        page_number=1,
        doc_id="test-doc",
        width_pt=612.0,
        height_pt=792.0,
        canonical_evidence_hash="sha256:def456",
        render_mode=render_mode,  # type: ignore[arg-type]
        fallback_image_ref="/img/p0001_fallback.png" if render_mode != "semantic" else None,
        page_confidence=0.85 if render_mode != "semantic" else 1.0,
        confidence_reasons=["low_text_density"] if render_mode != "semantic" else [],
        source_pdf_sha256="sha256:testpdfhash",
    )


# ---------------------------------------------------------------------------
# Fixture-based schema validation: model → JSON → validate against schema
# ---------------------------------------------------------------------------


class TestPrimitivePageEvidenceSchema:
    """Validate PrimitivePageEvidence against its checked-in JSON Schema."""

    def test_minimal_payload_validates(self) -> None:
        """A minimal PrimitivePageEvidence with only required fields passes."""
        model = PrimitivePageEvidence(page_number=1, doc_id="doc", width_pt=612.0, height_pt=792.0)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "PrimitivePageEvidence")

    def test_simple_fixture_validates(self) -> None:
        """Simple fixture (text only) passes schema."""
        model = _make_primitive_page_evidence(rich=False)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "PrimitivePageEvidence")

    def test_rich_fixture_validates(self) -> None:
        """Rich fixture (all primitive types + raster handle) passes schema."""
        model = _make_primitive_page_evidence(rich=True)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "PrimitivePageEvidence")

    def test_round_trip_preserves_data(self) -> None:
        """Serialize → deserialize round-trip preserves all fields."""
        original = _make_primitive_page_evidence(rich=True)
        payload = original.model_dump(mode="json")
        restored = PrimitivePageEvidence.model_validate(payload)
        assert restored == original

    def test_missing_required_field_rejected_by_schema(self) -> None:
        """Schema rejects payload missing required 'doc_id'."""
        payload = {"page_number": 1, "width_pt": 612.0, "height_pt": 792.0}
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "PrimitivePageEvidence")

    def test_invalid_bbox_rejected_by_schema(self) -> None:
        """Schema rejects bbox coordinate outside [0, 1]."""
        model = _make_primitive_page_evidence(rich=False)
        payload = model.model_dump(mode="json")
        payload["text_primitives"][0]["bbox_norm"]["x0"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "PrimitivePageEvidence")

    def test_nested_primitive_missing_required_rejected(self) -> None:
        """Schema rejects a text primitive missing required 'text' field."""
        payload: dict[str, Any] = {
            "page_number": 1,
            "doc_id": "doc",
            "width_pt": 612.0,
            "height_pt": 792.0,
            "text_primitives": [
                {
                    "primitive_id": "txt-0001",
                    "bbox_norm": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.2},
                    # "text" is missing — required
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "PrimitivePageEvidence")


class TestCanonicalPageEvidenceSchema:
    """Validate CanonicalPageEvidence against its checked-in JSON Schema."""

    def test_minimal_payload_validates(self) -> None:
        model = CanonicalPageEvidence(page_number=1, doc_id="doc", width_pt=612.0, height_pt=792.0)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "CanonicalPageEvidence")

    def test_full_fixture_validates(self) -> None:
        model = _make_canonical_page_evidence(with_content=True)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "CanonicalPageEvidence")

    def test_round_trip_preserves_data(self) -> None:
        original = _make_canonical_page_evidence(with_content=True)
        payload = original.model_dump(mode="json")
        restored = CanonicalPageEvidence.model_validate(payload)
        assert restored == original

    def test_missing_required_field_rejected(self) -> None:
        payload = {"page_number": 1, "width_pt": 612.0, "height_pt": 792.0}
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "CanonicalPageEvidence")

    def test_furniture_fraction_out_of_range_rejected(self) -> None:
        """Schema rejects furniture_fraction > 1.0."""
        model = _make_canonical_page_evidence()
        payload = model.model_dump(mode="json")
        payload["furniture_fraction"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "CanonicalPageEvidence")


class TestResolvedPageIRSchema:
    """Validate ResolvedPageIR against its checked-in JSON Schema."""

    def test_minimal_payload_validates(self) -> None:
        model = ResolvedPageIR(page_number=1, doc_id="doc", width_pt=612.0, height_pt=792.0)
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "ResolvedPageIR")

    def test_semantic_mode_validates(self) -> None:
        model = _make_resolved_page_ir(render_mode="semantic")
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "ResolvedPageIR")

    def test_hybrid_mode_validates(self) -> None:
        model = _make_resolved_page_ir(render_mode="hybrid")
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "ResolvedPageIR")

    def test_facsimile_mode_validates(self) -> None:
        model = _make_resolved_page_ir(render_mode="facsimile")
        payload = model.model_dump(mode="json")
        _validate_against_schema(payload, "ResolvedPageIR")

    def test_round_trip_preserves_data(self) -> None:
        original = _make_resolved_page_ir(render_mode="hybrid")
        payload = original.model_dump(mode="json")
        restored = ResolvedPageIR.model_validate(payload)
        assert restored == original

    def test_missing_required_field_rejected(self) -> None:
        payload = {"page_number": 1, "width_pt": 612.0, "height_pt": 792.0}
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "ResolvedPageIR")

    def test_invalid_render_mode_rejected(self) -> None:
        """Schema rejects an invalid render_mode enum value."""
        model = _make_resolved_page_ir()
        payload = model.model_dump(mode="json")
        payload["render_mode"] = "invalid_mode"
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "ResolvedPageIR")

    def test_confidence_out_of_range_rejected(self) -> None:
        """Schema rejects page_confidence > 1.0."""
        model = _make_resolved_page_ir()
        payload = model.model_dump(mode="json")
        payload["page_confidence"] = 2.0
        with pytest.raises(jsonschema.ValidationError):
            _validate_against_schema(payload, "ResolvedPageIR")


# ---------------------------------------------------------------------------
# Cross-model: Pydantic schema ↔ checked-in JSON Schema consistency
# ---------------------------------------------------------------------------


class TestSchemaConsistency:
    """Verify that Pydantic-generated schemas match checked-in schemas."""

    @pytest.mark.parametrize("schema_name,model_cls", ARCH3_MODELS)
    def test_pydantic_schema_matches_checked_in(
        self, schema_name: str, model_cls: type[Any]
    ) -> None:
        """The Pydantic model_json_schema matches the checked-in file."""
        pydantic_schema = model_cls.model_json_schema(mode="serialization")
        checked_in_schema = _load_schema(schema_name)
        assert pydantic_schema == checked_in_schema, (
            f"{schema_name}: checked-in schema drifted from Pydantic model. "
            f"Run `make schemas` to regenerate."
        )


# ---------------------------------------------------------------------------
# Integration: run V3 stages, read persisted artifacts, validate on disk
# ---------------------------------------------------------------------------


def _create_test_pdf(path: Path) -> None:
    """Create a simple single-page test PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Title", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text here.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _create_multipage_pdf(path: Path) -> None:
    """Create a multi-page test PDF for richer coverage."""
    doc = pymupdf.open()
    # Page 1: simple text
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text((72, 72), "Page One Title", fontsize=18, fontname="hebo")
    p1.insert_text((72, 110), "First page body text.", fontsize=11, fontname="helv")
    # Page 2: more text to simulate a harder page
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((72, 72), "Page Two Title", fontsize=18, fontname="hebo")
    p2.insert_text(
        (72, 110), "Second page body text with more content.", fontsize=11, fontname="helv"
    )
    p2.insert_text((72, 150), "Additional paragraph on page two.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_stage_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
) -> StageContext:
    """Create a StageContext for V3 pipeline execution."""
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id=run_id, architecture="v3"),  # type: ignore[arg-type]
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test", ru="Тест"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="rulebook-default",
                models="translate-default",
                symbols="aeon-core",
                glossary="aeon-core",
            ),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(profile_id="test", provider="gemini", model="gemini-2.0-flash"),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _run_v3_pipeline(ctx: StageContext) -> None:
    """Run the V3 evidence pipeline stages."""
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    CollectEvidenceStage().execute(ctx)
    ResolvePageIRStage().execute(ctx)


def _read_artifact_json(ctx: StageContext, stage_name: str, filename: str) -> dict[str, Any]:
    """Read a persisted artifact as raw JSON dict (bypassing Pydantic)."""
    stage_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, stage_name)
    path = stage_dir / filename
    assert path.exists(), f"Artifact not found: {path}"
    result: dict[str, Any] = json.loads(path.read_bytes())
    return result


class TestPersistedArtifactValidation:
    """Run the V3 pipeline and validate persisted artifacts on disk."""

    def test_single_page_primitive_evidence(self, tmp_path: Path) -> None:
        """Persisted PrimitivePageEvidence validates against schema."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_stage_context(tmp_path, pdf)
        _run_v3_pipeline(ctx)

        raw = _read_artifact_json(ctx, "extract_primitives", "evidence/p0001_primitive.json")
        _validate_against_schema(raw, "PrimitivePageEvidence")
        # Also round-trip through Pydantic
        model = PrimitivePageEvidence.model_validate(raw)
        assert model.page_number == 1
        assert model.doc_id == "test-doc"

    def test_single_page_canonical_evidence(self, tmp_path: Path) -> None:
        """Persisted CanonicalPageEvidence validates against schema."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_stage_context(tmp_path, pdf)
        _run_v3_pipeline(ctx)

        raw = _read_artifact_json(ctx, "collect_evidence", "evidence/p0001_canonical.json")
        _validate_against_schema(raw, "CanonicalPageEvidence")
        model = CanonicalPageEvidence.model_validate(raw)
        assert model.page_number == 1
        assert model.primitive_evidence_hash != ""

    def test_single_page_resolved_ir(self, tmp_path: Path) -> None:
        """Persisted ResolvedPageIR validates against schema."""
        pdf = tmp_path / "source.pdf"
        _create_test_pdf(pdf)
        ctx = _make_stage_context(tmp_path, pdf)
        _run_v3_pipeline(ctx)

        raw = _read_artifact_json(ctx, "resolve_page_ir", "resolved/p0001.json")
        _validate_against_schema(raw, "ResolvedPageIR")
        model = ResolvedPageIR.model_validate(raw)
        assert model.page_number == 1
        assert model.render_mode == "semantic"
        assert model.canonical_evidence_hash != ""

    def test_multipage_all_artifacts_validate(self, tmp_path: Path) -> None:
        """Multi-page PDF: every persisted artifact validates against its schema."""
        pdf = tmp_path / "source.pdf"
        _create_multipage_pdf(pdf)
        ctx = _make_stage_context(tmp_path, pdf)
        _run_v3_pipeline(ctx)

        PPE = PrimitivePageEvidence
        CPE = CanonicalPageEvidence
        RIR = ResolvedPageIR
        artifact_map: list[tuple[str, str, str, type[Any]]] = [
            ("extract_primitives", "evidence/p0001_primitive.json", "PrimitivePageEvidence", PPE),
            ("extract_primitives", "evidence/p0002_primitive.json", "PrimitivePageEvidence", PPE),
            ("collect_evidence", "evidence/p0001_canonical.json", "CanonicalPageEvidence", CPE),
            ("collect_evidence", "evidence/p0002_canonical.json", "CanonicalPageEvidence", CPE),
            ("resolve_page_ir", "resolved/p0001.json", "ResolvedPageIR", RIR),
            ("resolve_page_ir", "resolved/p0002.json", "ResolvedPageIR", RIR),
        ]

        for stage_name, filename, schema_name, model_cls in artifact_map:
            raw = _read_artifact_json(ctx, stage_name, filename)
            _validate_against_schema(raw, schema_name)
            model_cls.model_validate(raw)
