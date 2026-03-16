"""End-to-end integration test: run all 15 stages on a fixture PDF."""

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
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.qa_models import QASummary
from aeon_reader_pipeline.models.release_models import ReleaseManifest
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.models.site_bundle_models import (
    BuildArtifacts,
    BundlePage,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.apply_safe_fixes import ApplySafeFixesStage
from aeon_reader_pipeline.stages.build_reader import (
    BuildReaderStage,
    ReaderBuildManifest,
)
from aeon_reader_pipeline.stages.enrich_content import (
    DocumentSummary,
    EnrichContentStage,
    NavigationTree,
    SearchIndex,
)
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
from aeon_reader_pipeline.stages.package_release import PackageReleaseStage
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
            text=json.dumps(
                {"unit_id": data["unit_id"], "translations": translations}
            ),
            provider="mock",
            model="mock",
        )

    def provider_name(self) -> str:
        return "mock"


def _create_fixture_pdf(path: Path) -> None:
    """Create a multi-page fixture PDF with headings, body text, and a list."""
    doc = pymupdf.open()

    # Page 1 — heading + paragraphs
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One: Setup", fontsize=20, fontname="hebo")
    page.insert_text(
        (72, 120), "Players start by choosing a character.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 150), "Each character has unique abilities.", fontsize=11, fontname="helv"
    )

    # Page 2 — heading + list-like content
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Two: Combat", fontsize=20, fontname="hebo")
    page.insert_text(
        (72, 120), "Combat proceeds in rounds.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 150), "Roll dice to determine initiative.", fontsize=11, fontname="helv"
    )

    toc = [[1, "Chapter One: Setup", 1], [1, "Chapter Two: Combat", 2]]
    doc.set_toc(toc)
    doc.set_metadata({"title": "Fixture Rulebook", "author": "Test Suite"})
    doc.save(str(path))
    doc.close()


def _make_context(tmp_path: Path, pdf_path: Path) -> StageContext:
    configs_root = pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = configs_root.parent / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text(
        "Translate from {{ source_locale }} to {{ target_locale }}."
    )
    (prompts / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-e2e", ["fixture-doc"])

    return StageContext(
        run_id="run-e2e",
        doc_id="fixture-doc",
        pipeline_config=PipelineConfig(run_id="run-e2e"),
        document_config=DocumentConfig(
            doc_id="fixture-doc",
            slug="fixture-doc",
            source_pdf=str(pdf_path),
            titles=DocumentTitles(en="Fixture Rulebook", ru="\u0424\u0438\u043a\u0441\u0442\u0443\u0440\u0430"),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="test", models="test", symbols="test", glossary="test"
            ),
            build=DocumentBuild(route_base="/docs/fixture-doc"),
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


class TestFullPipeline:
    """Run all 15 stages and validate key artifacts at each boundary."""

    def test_full_pipeline_produces_release(self, tmp_path: Path) -> None:
        pdf = tmp_path / "fixture.pdf"
        _create_fixture_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        # Stage 1: Ingest
        IngestSourceStage().execute(ctx)

        # Stage 2: Extract
        ExtractPrimitivesStage().execute(ctx)

        # Stage 3: Normalize
        NormalizeLayoutStage().execute(ctx)
        page1 = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "normalize_layout", "pages/p0001.json", PageRecord
        )
        assert page1.page_number == 1
        assert len(page1.blocks) > 0

        # Stage 4: Resolve assets/symbols
        ResolveAssetsSymbolsStage().execute(ctx)

        # Stage 5: Plan translation
        PlanTranslationStage().execute(ctx)

        # Stage 6: Translate units
        translate = TranslateUnitsStage()
        translate.set_gateway(MockGateway())
        translate.execute(ctx)

        # Stage 7: Merge localization
        MergeLocalizationStage().execute(ctx)

        # Stage 8: Enrich content
        EnrichContentStage().execute(ctx)
        nav = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "enrich_content", "navigation.json", NavigationTree
        )
        assert nav.total_entries >= 1
        search_idx = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "enrich_content", "search_documents.json", SearchIndex
        )
        assert search_idx.total_documents >= 1
        doc_summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "enrich_content", "doc_summary.json", DocumentSummary
        )
        assert doc_summary.page_count == 2

        # Stage 9: Evaluate QA
        EvaluateQAStage().execute(ctx)
        qa = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "evaluate_qa", "summary.json", QASummary
        )
        assert qa.accepted is True
        assert qa.errors == 0

        # Stage 10: Apply safe fixes
        ApplySafeFixesStage().execute(ctx)

        # Stage 11: Export site bundle
        ExportSiteBundleStage().execute(ctx)
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/fixture-doc/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.doc_id == "fixture-doc"
        assert manifest.page_count == 2
        assert manifest.qa_accepted is True

        bundle_p1 = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "site_bundle/fixture-doc/pages/p0001.json",
            BundlePage,
        )
        assert bundle_p1.page_number == 1
        # Verify internal fields are stripped
        p1_data = bundle_p1.model_dump()
        assert "source_pdf_sha256" not in p1_data
        assert "fingerprint" not in p1_data

        build_artifacts = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            "build_artifacts.json",
            BuildArtifacts,
        )
        assert build_artifacts.total_artifacts >= 4  # 2 pages + nav + search + manifest

        # Stage 12: Build reader
        BuildReaderStage().execute(ctx)
        build = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "build_reader", "build_manifest.json", ReaderBuildManifest
        )
        assert build.bundle_page_count == 2
        assert len(build.routes) == 3  # doc root + 2 pages

        # Stage 13: Index search
        IndexSearchStage().execute(ctx)
        search_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "index_search",
            "search_index_manifest.json",
            SearchIndexManifest,
        )
        assert search_manifest.total_documents >= 1

        # Stage 14: Package release
        PackageReleaseStage().execute(ctx)
        release = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "package_release",
            "release_manifest.json",
            ReleaseManifest,
        )
        assert release.all_accepted is True
        assert release.total_documents == 1
        assert release.release_id.startswith("rel-")
