"""Tests for the index_search stage."""

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
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.export_site_bundle import ExportSiteBundleStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.index_search import (
    IndexSearchStage,
    SearchIndexManifest,
)
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
    configs_root = tmp_path / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = tmp_path / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    (tmp_path / "apps" / "reader" / "generated").mkdir(parents=True, exist_ok=True)

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
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
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
    ctx.llm_gateway = MockGateway()
    TranslateUnitsStage().execute(ctx)
    MergeLocalizationStage().execute(ctx)
    EnrichContentStage().execute(ctx)
    EvaluateQAStage().execute(ctx)
    ExportSiteBundleStage().execute(ctx)


class TestIndexSearchStage:
    def test_produces_search_index_manifest(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_export(ctx)
        IndexSearchStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "index_search",
            "search_index_manifest.json",
            SearchIndexManifest,
        )
        assert manifest.doc_id == "test-doc"
        assert manifest.run_id == "run-001"
        assert manifest.total_documents > 0
        assert manifest.pages_with_content > 0
        assert manifest.index_status == "search-data-validated"

    def test_records_document_kinds(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_export(ctx)
        IndexSearchStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "index_search",
            "search_index_manifest.json",
            SearchIndexManifest,
        )
        assert len(manifest.kinds) > 0
        assert all(v > 0 for v in manifest.kinds.values())

    def test_handles_missing_search_data(self, tmp_path: Path) -> None:
        """Stage should not crash when search documents are absent."""
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        # Run full pipeline including export, then delete search_documents.json
        # to simulate a bundle that was exported without search data.
        _run_through_export(ctx)

        # Remove search documents to simulate missing data
        export_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "export_site_bundle")
        search_file = export_dir / "site_bundle" / ctx.doc_id / "search_documents.json"
        if search_file.exists():
            search_file.unlink()

        IndexSearchStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "index_search",
            "search_index_manifest.json",
            SearchIndexManifest,
        )
        assert manifest.total_documents == 0
        assert manifest.index_status == "no-search-data"

    def test_stage_registration(self) -> None:
        stage = IndexSearchStage()
        assert stage.name == "index_search"
        assert stage.version == "2.0.0"
