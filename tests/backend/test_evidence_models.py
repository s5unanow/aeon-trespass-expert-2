"""Tests for Architecture 3 evidence-layer contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    DocumentFurnitureProfile,
    DrawingPrimitiveEvidence,
    FontSummary,
    FurnitureCandidate,
    ImagePrimitiveEvidence,
    NormalizedBBox,
    PrimitivePageEvidence,
    ResolvedPageIR,
    TablePrimitiveEvidence,
    TemplateAssignment,
    TextPrimitiveEvidence,
)


class TestNormalizedBBox:
    def test_basic(self) -> None:
        bbox = NormalizedBBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)
        assert bbox.x0 == 0.0
        assert bbox.y1 == 1.0


class TestPrimitiveEvidence:
    def test_text_primitive(self) -> None:
        tp = TextPrimitiveEvidence(
            primitive_id="text:p0001:003",
            bbox_norm=NormalizedBBox(x0=0.1, y0=0.2, x1=0.9, y1=0.3),
            text="Hello world",
            line_count=1,
            font_name="Arial",
            font_size=12.0,
        )
        assert tp.primitive_id == "text:p0001:003"
        assert tp.text == "Hello world"

    def test_image_primitive(self) -> None:
        ip = ImagePrimitiveEvidence(
            primitive_id="image:p0001:000",
            bbox_norm=NormalizedBBox(x0=0.0, y0=0.5, x1=0.5, y1=1.0),
            content_hash="abc123",
            width_px=640,
            height_px=480,
        )
        assert ip.content_hash == "abc123"

    def test_table_primitive(self) -> None:
        tp = TablePrimitiveEvidence(
            primitive_id="table:p0001:000",
            bbox_norm=NormalizedBBox(x0=0.1, y0=0.1, x1=0.9, y1=0.5),
            rows=3,
            cols=4,
            cell_count=12,
        )
        assert tp.rows == 3 and tp.cols == 4

    def test_drawing_primitive(self) -> None:
        dp = DrawingPrimitiveEvidence(
            primitive_id="drawing:p0001:000",
            bbox_norm=NormalizedBBox(x0=0.0, y0=0.0, x1=0.1, y1=0.1),
            path_count=5,
            is_decorative=True,
        )
        assert dp.is_decorative


class TestPrimitivePageEvidence:
    def test_empty_page(self) -> None:
        ppe = PrimitivePageEvidence(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
        )
        assert ppe.page_number == 1
        assert ppe.text_primitives == []
        assert ppe.extraction_method == "pdfplumber"

    def test_page_with_primitives(self) -> None:
        ppe = PrimitivePageEvidence(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            source_pdf_sha256="deadbeef",
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.1, y0=0.1, x1=0.9, y1=0.2),
                    text="Title",
                ),
            ],
            image_primitives=[
                ImagePrimitiveEvidence(
                    primitive_id="image:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.2, y0=0.3, x1=0.8, y1=0.7),
                    content_hash="abc123",
                ),
            ],
            char_count=5,
        )
        assert len(ppe.text_primitives) == 1
        assert len(ppe.image_primitives) == 1
        assert ppe.char_count == 5

    def test_json_roundtrip(self) -> None:
        ppe = PrimitivePageEvidence(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            text_primitives=[
                TextPrimitiveEvidence(
                    primitive_id="text:p0001:000",
                    bbox_norm=NormalizedBBox(x0=0.1, y0=0.1, x1=0.9, y1=0.2),
                    text="Hello",
                    font_name="Helvetica",
                    font_size=12.0,
                ),
            ],
            font_summary=FontSummary(
                dominant_font="Helvetica",
                dominant_size=12.0,
                unique_font_count=1,
            ),
        )
        data = ppe.model_dump(mode="json")
        restored = PrimitivePageEvidence.model_validate(data)
        assert restored.page_number == 1
        assert len(restored.text_primitives) == 1
        assert restored.text_primitives[0].text == "Hello"
        assert restored.font_summary.dominant_font == "Helvetica"


class TestCanonicalPageEvidence:
    def test_defaults(self) -> None:
        cpe = CanonicalPageEvidence(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
        )
        assert cpe.estimated_column_count == 1
        assert not cpe.has_tables
        assert cpe.furniture_fraction == 0.0
        assert cpe.furniture_ids == []
        assert cpe.template_id == ""

    def test_with_signals(self) -> None:
        cpe = CanonicalPageEvidence(
            page_number=5,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            primitive_evidence_hash="sha256:abc123",
            estimated_column_count=2,
            has_tables=True,
            has_figures=True,
            furniture_fraction=0.15,
            furniture_ids=["furn:header:000", "furn:footer:001"],
            template_id="tpl:abc12345",
        )
        assert cpe.estimated_column_count == 2
        assert cpe.has_tables
        assert cpe.primitive_evidence_hash == "sha256:abc123"
        assert len(cpe.furniture_ids) == 2
        assert cpe.template_id == "tpl:abc12345"

    def test_json_roundtrip(self) -> None:
        cpe = CanonicalPageEvidence(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            has_callouts=True,
            furniture_ids=["furn:header:000"],
            template_id="tpl:test",
        )
        data = cpe.model_dump(mode="json")
        restored = CanonicalPageEvidence.model_validate(data)
        assert restored.has_callouts
        assert restored.furniture_ids == ["furn:header:000"]
        assert restored.template_id == "tpl:test"


class TestResolvedPageIR:
    def test_defaults(self) -> None:
        ir = ResolvedPageIR(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
        )
        assert ir.render_mode == "semantic"
        assert ir.page_confidence == 1.0
        assert ir.fallback_image_ref is None

    def test_render_modes(self) -> None:
        for mode in ("semantic", "hybrid", "facsimile"):
            ir = ResolvedPageIR(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                render_mode=mode,
            )
            assert ir.render_mode == mode

    def test_with_confidence(self) -> None:
        ir = ResolvedPageIR(
            page_number=3,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            canonical_evidence_hash="sha256:def456",
            render_mode="hybrid",
            fallback_image_ref="page_003_fallback.png",
            page_confidence=0.45,
            confidence_reasons=["multi-column ambiguity", "overlapping regions"],
        )
        assert ir.render_mode == "hybrid"
        assert ir.page_confidence == 0.45
        assert len(ir.confidence_reasons) == 2

    def test_json_roundtrip(self) -> None:
        ir = ResolvedPageIR(
            page_number=1,
            doc_id="test-doc",
            width_pt=612.0,
            height_pt=792.0,
            render_mode="facsimile",
            fallback_image_ref="p0001_fallback.png",
            page_confidence=0.2,
            confidence_reasons=["dense layout"],
        )
        data = ir.model_dump(mode="json")
        restored = ResolvedPageIR.model_validate(data)
        assert restored.render_mode == "facsimile"
        assert restored.fallback_image_ref == "p0001_fallback.png"
        assert restored.page_confidence == 0.2


class TestValidationConstraints:
    def test_normalized_bbox_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            NormalizedBBox(x0=-0.1, y0=0.0, x1=1.0, y1=1.0)
        with pytest.raises(ValidationError):
            NormalizedBBox(x0=0.0, y0=0.0, x1=1.5, y1=1.0)

    def test_page_confidence_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ResolvedPageIR(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                page_confidence=1.5,
            )
        with pytest.raises(ValidationError):
            ResolvedPageIR(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                page_confidence=-0.1,
            )

    def test_furniture_fraction_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalPageEvidence(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                furniture_fraction=2.0,
            )

    def test_invalid_render_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResolvedPageIR(
                page_number=1,
                doc_id="d",
                width_pt=100,
                height_pt=100,
                render_mode="invalid",  # type: ignore[arg-type]
            )

    def test_furniture_candidate_confidence_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            FurnitureCandidate(
                candidate_id="furn:header:000",
                furniture_type="header",
                bbox_norm=NormalizedBBox(x0=0.1, y0=0.02, x1=0.9, y1=0.05),
                source_primitive_kind="text",
                confidence=1.5,
            )

    def test_furniture_candidate_repetition_rate_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            FurnitureCandidate(
                candidate_id="furn:header:000",
                furniture_type="header",
                bbox_norm=NormalizedBBox(x0=0.1, y0=0.02, x1=0.9, y1=0.05),
                source_primitive_kind="text",
                repetition_rate=-0.1,
            )


class TestFurnitureCandidate:
    def test_basic(self) -> None:
        fc = FurnitureCandidate(
            candidate_id="furn:header:000",
            furniture_type="header",
            bbox_norm=NormalizedBBox(x0=0.1, y0=0.02, x1=0.9, y1=0.05),
            source_primitive_kind="text",
            page_numbers=[1, 2, 3],
            repetition_rate=1.0,
            text_sample="Header Text",
        )
        assert fc.candidate_id == "furn:header:000"
        assert fc.furniture_type == "header"
        assert fc.page_numbers == [1, 2, 3]

    def test_json_roundtrip(self) -> None:
        fc = FurnitureCandidate(
            candidate_id="furn:footer:001",
            furniture_type="footer",
            bbox_norm=NormalizedBBox(x0=0.1, y0=0.95, x1=0.9, y1=0.99),
            source_primitive_kind="text",
            page_numbers=[1, 2],
            repetition_rate=0.8,
            confidence=0.9,
            text_sample="Footer",
        )
        data = fc.model_dump(mode="json")
        restored = FurnitureCandidate.model_validate(data)
        assert restored == fc


class TestTemplateAssignment:
    def test_basic(self) -> None:
        ta = TemplateAssignment(
            template_id="tpl:abc12345",
            page_numbers=[1, 2, 3],
            furniture_ids=["furn:header:000", "furn:footer:001"],
            description="Standard body page",
        )
        assert ta.template_id == "tpl:abc12345"
        assert len(ta.page_numbers) == 3

    def test_json_roundtrip(self) -> None:
        ta = TemplateAssignment(
            template_id="tpl:xyz",
            page_numbers=[1],
            furniture_ids=["furn:header:000"],
        )
        data = ta.model_dump(mode="json")
        restored = TemplateAssignment.model_validate(data)
        assert restored == ta


class TestDocumentFurnitureProfile:
    def test_empty_profile(self) -> None:
        profile = DocumentFurnitureProfile(
            doc_id="test",
            total_pages_analyzed=0,
        )
        assert profile.furniture_candidates == []
        assert profile.templates == []
        assert profile.detection_version == "0.1.0"

    def test_json_roundtrip(self) -> None:
        profile = DocumentFurnitureProfile(
            doc_id="test",
            total_pages_analyzed=5,
            furniture_candidates=[
                FurnitureCandidate(
                    candidate_id="furn:header:000",
                    furniture_type="header",
                    bbox_norm=NormalizedBBox(x0=0.1, y0=0.02, x1=0.9, y1=0.05),
                    source_primitive_kind="text",
                    page_numbers=[1, 2, 3, 4, 5],
                    repetition_rate=1.0,
                ),
            ],
            templates=[
                TemplateAssignment(
                    template_id="tpl:abc",
                    page_numbers=[1, 2, 3, 4, 5],
                    furniture_ids=["furn:header:000"],
                ),
            ],
        )
        data = profile.model_dump(mode="json")
        restored = DocumentFurnitureProfile.model_validate(data)
        assert restored == profile
