"""Tests for the merge_localization stage."""

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
    PageRecord,
    ParagraphBlock,
    TextRun,
)
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.merge_localization import (
    MergeLocalizationStage,
    _build_translation_map,
    _merge_blocks,
)
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    ResolveAssetsSymbolsStage,
)
from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage


class MockGateway(LlmGateway):
    """Mock LLM gateway for testing."""

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        data = json.loads(user_prompt)
        unit_id = data["unit_id"]
        translations = []
        for node in data["text_nodes"]:
            translations.append(
                {
                    "inline_id": node["inline_id"],
                    "ru_text": f"[RU] {node['source_text']}",
                }
            )
        response = json.dumps({"unit_id": unit_id, "translations": translations})
        return LlmResponse(text=response, provider="mock", model="mock-model")

    def provider_name(self) -> str:
        return "mock"


def _make_context(
    tmp_path: Path,
    source_pdf_path: Path,
    *,
    doc_id: str = "test-doc",
    run_id: str = "run-001",
) -> StageContext:
    configs_root = source_pdf_path.parent / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts_root = configs_root.parent / "prompts" / "translate" / "v1"
    prompts_root.mkdir(parents=True, exist_ok=True)
    (prompts_root / "system.j2").write_text(
        "Translate from {{ source_locale }} to {{ target_locale }}."
    )
    (prompts_root / "response_schema.json").write_text("{}")

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run(run_id, [doc_id])

    return StageContext(
        run_id=run_id,
        doc_id=doc_id,
        pipeline_config=PipelineConfig(run_id=run_id),
        document_config=DocumentConfig(
            doc_id=doc_id,
            slug="test-doc",
            source_pdf=str(source_pdf_path),
            titles=DocumentTitles(en="Test", ru="\u0422\u0435\u0441\u0442"),
            edition="v1",
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(
                rules="test",
                models="test",
                symbols="test",
                glossary="test",
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


def _create_simple_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Title", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Body paragraph text.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_through_translate(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)
    stage = TranslateUnitsStage()
    stage.set_gateway(MockGateway())
    stage.execute(ctx)


class TestMergeLocalizationUnit:
    def test_build_translation_map(self) -> None:
        from aeon_reader_pipeline.models.translation_models import (
            TextNode,
            TranslatedNode,
            TranslationResult,
            TranslationUnit,
        )

        units = [
            TranslationUnit(
                unit_id="u1",
                doc_id="doc",
                page_number=1,
                text_nodes=[
                    TextNode(inline_id="b1:i000", source_text="Hello"),
                ],
            ),
        ]
        results = [
            TranslationResult(
                unit_id="u1",
                translations=[
                    TranslatedNode(
                        inline_id="b1:i000",
                        ru_text="\u041f\u0440\u0438\u0432\u0435\u0442",
                    ),
                ],
            ),
        ]
        mapping = _build_translation_map(units, results)
        assert "b1:i000" in mapping
        assert mapping["b1:i000"] == "\u041f\u0440\u0438\u0432\u0435\u0442"

    def test_merge_blocks_injects_ru_text(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Hello")],
            ),
        ]
        mapping = {"b1:i000": "\u041f\u0440\u0438\u0432\u0435\u0442"}
        merged = _merge_blocks(blocks, mapping)
        para = merged[0]
        assert isinstance(para, ParagraphBlock)
        run = para.content[0]
        assert isinstance(run, TextRun)
        assert run.ru_text == "\u041f\u0440\u0438\u0432\u0435\u0442"

    def test_merge_preserves_source_text(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Hello")],
            ),
        ]
        mapping = {"b1:i000": "\u041f\u0440\u0438\u0432\u0435\u0442"}
        merged = _merge_blocks(blocks, mapping)
        run = merged[0].content[0]
        assert isinstance(run, TextRun)
        assert run.text == "Hello"

    def test_merge_skips_unmatched(self) -> None:
        blocks = [
            ParagraphBlock(
                block_id="b1",
                content=[TextRun(text="Hello")],
            ),
        ]
        merged = _merge_blocks(blocks, {})
        run = merged[0].content[0]
        assert isinstance(run, TextRun)
        assert run.ru_text is None


class TestMergeLocalizationIntegration:
    def test_merge_produces_localized_pages(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_translate(ctx)
        MergeLocalizationStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "merge_localization",
            "pages/p0001.json",
            PageRecord,
        )
        # At least some text runs should have ru_text
        has_ru = False
        for block in record.blocks:
            if hasattr(block, "content"):
                for node in block.content:
                    if isinstance(node, TextRun) and node.ru_text:
                        has_ru = True
        assert has_ru

    def test_merge_preserves_structure(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_translate(ctx)
        MergeLocalizationStage().execute(ctx)

        record = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "merge_localization",
            "pages/p0001.json",
            PageRecord,
        )
        # At least one block with translated content
        assert len(record.blocks) >= 1

    def test_stage_registration(self) -> None:
        stage = MergeLocalizationStage()
        assert stage.name == "merge_localization"
