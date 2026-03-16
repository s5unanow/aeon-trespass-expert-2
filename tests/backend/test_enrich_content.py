"""Tests for the enrich_content stage."""

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
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.enrich_content import (
    DocumentSummary,
    EnrichContentStage,
    NavigationTree,
    SearchIndex,
    _build_navigation,
    _build_search_documents,
    _compute_coverage,
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
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
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
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    page.insert_text((72, 160), "Another paragraph.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_through_merge(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)
    stage = TranslateUnitsStage()
    stage.set_gateway(MockGateway())
    stage.execute(ctx)
    MergeLocalizationStage().execute(ctx)


class TestEnrichContentUnit:
    def test_build_navigation_from_headings(self) -> None:
        pages = [
            PageRecord(
                page_number=1,
                doc_id="doc",
                width_pt=612,
                height_pt=792,
                blocks=[
                    HeadingBlock(
                        block_id="h1",
                        level=1,
                        content=[TextRun(text="Chapter 1")],
                        anchor="doc:p0001:chapter-1",
                    ),
                    HeadingBlock(
                        block_id="h2",
                        level=2,
                        content=[TextRun(text="Section 1.1")],
                        anchor="doc:p0001:section-11",
                    ),
                ],
            ),
        ]
        nav = _build_navigation(pages, "doc")
        assert nav.total_entries == 2
        assert len(nav.entries) == 1  # nested
        assert len(nav.entries[0].children) == 1

    def test_build_search_documents(self) -> None:
        from aeon_reader_pipeline.models.ir_models import ParagraphBlock

        pages = [
            PageRecord(
                page_number=1,
                doc_id="doc",
                width_pt=612,
                height_pt=792,
                blocks=[
                    HeadingBlock(
                        block_id="h1",
                        level=1,
                        content=[TextRun(text="Title")],
                        anchor="a1",
                    ),
                    ParagraphBlock(
                        block_id="p1",
                        content=[TextRun(text="Body text", ru_text="[RU]")],
                    ),
                ],
            ),
        ]
        docs = _build_search_documents(pages, "doc")
        assert len(docs) >= 2  # heading + paragraph
        body_doc = next(d for d in docs if d.kind == "paragraph")
        assert body_doc.content_en == "Body text"
        assert body_doc.content_ru == "[RU]"

    def test_compute_coverage_full(self) -> None:
        from aeon_reader_pipeline.models.ir_models import ParagraphBlock

        pages = [
            PageRecord(
                page_number=1,
                doc_id="doc",
                width_pt=612,
                height_pt=792,
                blocks=[
                    ParagraphBlock(
                        block_id="p1",
                        content=[TextRun(text="Hello", ru_text="RU")],
                    ),
                ],
            ),
        ]
        assert _compute_coverage(pages) == 1.0

    def test_compute_coverage_partial(self) -> None:
        from aeon_reader_pipeline.models.ir_models import ParagraphBlock

        pages = [
            PageRecord(
                page_number=1,
                doc_id="doc",
                width_pt=612,
                height_pt=792,
                blocks=[
                    ParagraphBlock(
                        block_id="p1",
                        content=[
                            TextRun(text="Hello", ru_text="RU"),
                            TextRun(text="World"),
                        ],
                    ),
                ],
            ),
        ]
        assert _compute_coverage(pages) == 0.5


class TestEnrichContentIntegration:
    def test_enrich_produces_all_artifacts(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_merge(ctx)
        EnrichContentStage().execute(ctx)

        # Navigation
        nav = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "navigation.json",
            NavigationTree,
        )
        assert nav.total_entries >= 1

        # Search index
        search = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "search_documents.json",
            SearchIndex,
        )
        assert search.total_documents >= 1

        # Doc summary
        summary = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "doc_summary.json",
            DocumentSummary,
        )
        assert summary.page_count == 1
        assert summary.title_en == "Test Doc"

    def test_enrich_writes_pages(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_merge(ctx)
        EnrichContentStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "enrich_content",
            "pages/p0001.json",
            PageRecord,
        )
        assert record.page_number == 1
        assert len(record.blocks) > 0

    def test_stage_registration(self) -> None:
        stage = EnrichContentStage()
        assert stage.name == "enrich_content"
        assert stage.version == "1.0.0"
