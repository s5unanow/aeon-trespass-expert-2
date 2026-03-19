"""Multi-document hardening test: two docs through export and catalog assembly."""

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
from aeon_reader_pipeline.models.site_bundle_models import (
    CatalogEntry,
    CatalogManifest,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.apply_safe_fixes import ApplySafeFixesStage
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


def _create_pdf(path: Path, title: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), title, fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _make_context(
    tmp_path: Path,
    store: ArtifactStore,
    pdf_path: Path,
    doc_id: str,
    title_en: str,
    title_ru: str,
) -> StageContext:
    configs_root = pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = configs_root.parent / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    return StageContext(
        run_id="run-multi",
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id="run-multi"),
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug=doc_id,
            source_pdf=str(pdf_path),
            titles=DocumentTitles(en=title_en, ru=title_ru),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base=f"/docs/{doc_id}"),
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
    ApplySafeFixesStage().execute(ctx)
    ExportSiteBundleStage().execute(ctx)


class TestMultiDocument:
    def test_two_docs_export_and_catalog(self, tmp_path: Path) -> None:
        """Run two documents through the pipeline and assemble a catalog."""
        store = ArtifactStore(tmp_path / "artifacts")
        store.create_run("run-multi", ["doc-core", "doc-odyssey"])

        # Document 1
        pdf1 = tmp_path / "core.pdf"
        _create_pdf(pdf1, "Core Rulebook")
        ctx1 = _make_context(
            tmp_path,
            store,
            pdf1,
            "doc-core",
            "Core Rulebook",
            "Основные правила",
        )
        _run_through_export(ctx1)

        # Document 2
        pdf2 = tmp_path / "odyssey.pdf"
        _create_pdf(pdf2, "Odyssey Expansion")
        ctx2 = _make_context(
            tmp_path,
            store,
            pdf2,
            "doc-odyssey",
            "Odyssey Expansion",
            "\u041e\u0434\u0438\u0441\u0441\u0435\u044f",
        )
        _run_through_export(ctx2)

        # Verify both bundles exist
        m1 = store.read_artifact(
            "run-multi",
            "doc-core",
            "export_site_bundle",
            "site_bundle/doc-core/bundle_manifest.json",
            SiteBundleManifest,
        )
        m2 = store.read_artifact(
            "run-multi",
            "doc-odyssey",
            "export_site_bundle",
            "site_bundle/doc-odyssey/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert m1.doc_id == "doc-core"
        assert m2.doc_id == "doc-odyssey"

        # Assemble a catalog from the two manifests
        catalog = CatalogManifest(
            documents=[
                CatalogEntry(
                    doc_id=m.doc_id,
                    slug=m.doc_id,
                    title_en=m.title_en,
                    title_ru=m.title_ru,
                    route_base=m.route_base,
                    page_count=m.page_count,
                    translation_coverage=m.translation_coverage,
                )
                for m in [m1, m2]
            ],
            total_documents=2,
        )
        assert catalog.total_documents == 2
        assert {d.doc_id for d in catalog.documents} == {"doc-core", "doc-odyssey"}
