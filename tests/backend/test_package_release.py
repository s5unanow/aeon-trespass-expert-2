"""Tests for the package_release stage."""

from __future__ import annotations

import json
import tarfile
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
from aeon_reader_pipeline.models.release_models import ReleaseManifest
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.build_reader import BuildReaderStage
from aeon_reader_pipeline.stages.enrich_content import EnrichContentStage
from aeon_reader_pipeline.stages.evaluate_qa import EvaluateQAStage
from aeon_reader_pipeline.stages.export_site_bundle import ExportSiteBundleStage
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.index_search import IndexSearchStage
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


def _run_full_pipeline(ctx: StageContext) -> None:
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
    BuildReaderStage().execute(ctx)
    IndexSearchStage().execute(ctx)


class TestPackageReleaseStage:
    def test_accepted_release(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_full_pipeline(ctx)
        PackageReleaseStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "package_release",
            "release_manifest.json",
            ReleaseManifest,
        )
        assert manifest.all_accepted is True
        assert manifest.total_documents == 1
        assert manifest.documents[0].doc_id == "test-doc"
        assert manifest.release_id.startswith("rel-")

    def test_release_creates_archive(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_full_pipeline(ctx)
        PackageReleaseStage().execute(ctx)

        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "package_release",
            "release_manifest.json",
            ReleaseManifest,
        )
        assert manifest.artifact_path is not None
        assert manifest.artifact_size_bytes is not None
        assert manifest.artifact_size_bytes > 0
        assert manifest.artifact_sha256 is not None

        # Verify archive is a valid tar.gz
        stage_dir = ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "package_release")
        archive_path = stage_dir / manifest.artifact_path
        assert archive_path.exists()

        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
            assert "release_manifest.json" in names
            # Bundle content should be under doc_id/
            bundle_files = [n for n in names if n.startswith("test-doc/")]
            assert len(bundle_files) > 0

    def test_stage_registration(self) -> None:
        stage = PackageReleaseStage()
        assert stage.name == "package_release"
        assert stage.version == "2.0.0"
