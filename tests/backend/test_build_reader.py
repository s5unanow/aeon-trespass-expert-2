"""Tests for the build_reader stage."""

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
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.apply_safe_fixes import ApplySafeFixesStage
from aeon_reader_pipeline.stages.build_reader import (
    BuildReaderStage,
    ReaderBuildManifest,
)
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.export_site_bundle import ExportSiteBundleStage
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
    page.insert_text((72, 120), "Body text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_through_export(ctx: StageContext) -> None:
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
    ExportSiteBundleStage().execute(ctx)


class TestBuildReaderStage:
    def test_produces_build_manifest(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_export(ctx)
        BuildReaderStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "build_reader",
            "build_manifest.json",
            ReaderBuildManifest,
        )
        assert manifest.doc_id == "test-doc"
        assert manifest.bundle_page_count == 1
        assert manifest.build_status == "manifest-only"
        assert len(manifest.routes) == 2  # doc root + 1 page

    def test_stage_registration(self) -> None:
        stage = BuildReaderStage()
        assert stage.name == "build_reader"
        assert stage.version == "1.0.0"
