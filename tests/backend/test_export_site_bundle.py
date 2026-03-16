"""Tests for the export_site_bundle stage."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
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
from aeon_reader_pipeline.models.ir_models import (
    HeadingBlock,
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.models.site_bundle_models import (
    BuildArtifacts,
    BundlePage,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.apply_safe_fixes import ApplySafeFixesStage
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.export_site_bundle import (
    ExportSiteBundleStage,
    convert_page_to_bundle,
)
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.merge_localization import MergeLocalizationStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    ResolveAssetsSymbolsStage,
)
from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage


class MockGateway(LlmGateway):
    def translate(
        self, system_prompt: str, user_prompt: str, model_profile: ModelProfile
    ) -> LlmResponse:
        data = json.loads(user_prompt)
        translations = [
            {"inline_id": n["inline_id"], "ru_text": f"[RU] {n['source_text']}"}
            for n in data["text_nodes"]
        ]
        return LlmResponse(
            text=json.dumps({"unit_id": data["unit_id"], "translations": translations}),
            provider="mock",
            model="mock",
        )

    def provider_name(self) -> str:
        return "mock"


def _make_context(tmp_path: Path, source_pdf_path: Path) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = configs_root.parent / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text(
        "Translate from {{ source_locale }} to {{ target_locale }}."
    )
    (prompts / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-001", ["test-doc"])

    return StageContext(
        run_id="run-001",
        doc_id="test-doc",
        pipeline_config=PipelineConfig(run_id="run-001"),
        document_config=DocumentConfig(
            doc_id="test-doc",
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test Doc", ru="\u0422\u0435\u0441\u0442"),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="test", models="test", symbols="test", glossary="test"
            ),
            build=DocumentBuild(route_base="/docs/test-doc"),
        ),
        rule_profile=RuleProfile(profile_id="test"),
        model_profile=ModelProfile(
            profile_id="test",
            provider="gemini",
            model="gemini-2.0-flash",
            prompt_bundle="translate-v1",
        ),
        symbol_pack=SymbolPack(pack_id="test", version="1.0.0"),
        glossary_pack=GlossaryPack(pack_id="test", version="1.0.0"),
        patch_set=None,
        artifact_store=store,
        configs_root=configs_root,
    )


def _create_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_through_safe_fixes(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)
    stage = TranslateUnitsStage()
    stage.set_gateway(MockGateway())
    stage.execute(ctx)
    MergeLocalizationStage().execute(ctx)
    EnrichContentStage().execute(ctx)
    EvaluateQAStage().execute(ctx)
    ApplySafeFixesStage().execute(ctx)


class TestConvertPageToBundle:
    def test_strips_internal_fields(self) -> None:
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            source_pdf_sha256="abc123",
            fingerprint="fp123",
            blocks=[
                HeadingBlock(
                    block_id="h1",
                    level=1,
                    content=[TextRun(text="Title", font_name="Arial", font_size=18.0)],
                    source_block_index=0,
                ),
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Body", ru_text="[RU]", font_name="Times", font_size=11.0)],
                    source_block_index=1,
                ),
            ],
        )
        bundle = convert_page_to_bundle(record)
        data = bundle.model_dump()

        # No internal provenance
        assert "source_pdf_sha256" not in data
        assert "fingerprint" not in data

        # No source_block_index
        for block in data["blocks"]:
            assert "source_block_index" not in block

        # No font fields
        for block in data["blocks"]:
            if "content" in block:
                for node in block["content"]:
                    assert "font_name" not in node
                    assert "font_size" not in node

        # Content preserved
        assert bundle.page_number == 1
        assert len(bundle.blocks) == 2

    def test_preserves_text_content(self) -> None:
        record = PageRecord(
            page_number=1,
            doc_id="doc",
            width_pt=612,
            height_pt=792,
            blocks=[
                ParagraphBlock(
                    block_id="p1",
                    content=[TextRun(text="Hello", ru_text="RU Hello", bold=True)],
                ),
            ],
        )
        bundle = convert_page_to_bundle(record)
        block = bundle.blocks[0]
        assert hasattr(block, "content")
        content = block.content  # type: ignore[union-attr]
        assert len(content) == 1
        assert content[0].text == "Hello"
        assert content[0].ru_text == "RU Hello"
        assert content[0].bold is True


class TestExportSiteBundleIntegration:
    def test_exports_all_artifacts(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_safe_fixes(ctx)
        ExportSiteBundleStage().execute(ctx)

        # Bundle manifest
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.doc_id == "test-doc"
        assert manifest.page_count == 1
        assert manifest.title_en == "Test Doc"
        assert manifest.route_base == "/docs/test-doc"
        assert manifest.qa_accepted is True

        # Bundle page
        page = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/test-doc/pages/p0001.json",
            BundlePage,
        )
        assert page.page_number == 1
        assert len(page.blocks) > 0

        # Build artifacts inventory
        build = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "build_artifacts.json",
            BuildArtifacts,
        )
        assert build.total_artifacts >= 3  # pages + nav + manifest at minimum

    def test_stage_registration(self) -> None:
        stage = ExportSiteBundleStage()
        assert stage.name == "export_site_bundle"
        assert stage.version == "1.0.0"
