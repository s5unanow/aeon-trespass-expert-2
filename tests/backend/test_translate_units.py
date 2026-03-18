"""Tests for the translate_units stage."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from aeon_reader_pipeline.io.artifact_store import ArtifactStore
from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
from aeon_reader_pipeline.llm.translation_memory import TranslationMemory
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
from aeon_reader_pipeline.models.translation_models import (
    TranslationPlan,
    TranslationResult,
    TranslationStageSummary,
    TranslationUnit,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.extract_primitives import ExtractPrimitivesStage
from aeon_reader_pipeline.stages.ingest_source import IngestSourceStage
from aeon_reader_pipeline.stages.normalize_layout import NormalizeLayoutStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import ResolveAssetsSymbolsStage
from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage


class MockGateway(LlmGateway):
    """Mock LLM gateway that returns deterministic translations."""

    def __init__(self, *, fail: bool = False, bad_json: bool = False) -> None:
        self._fail = fail
        self._bad_json = bad_json

    def translate(
        self,
        system_prompt: str,
        user_prompt: str,
        model_profile: ModelProfile,
    ) -> LlmResponse:
        if self._fail:
            raise RuntimeError("Mock LLM failure")

        if self._bad_json:
            return LlmResponse(text="not valid json", provider="mock", model="mock-model")

        # Parse the user prompt to extract unit_id and text_nodes
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
        return LlmResponse(
            text=response,
            input_tokens=100,
            output_tokens=50,
            latency_ms=200,
            provider="mock",
            model="mock-model",
        )

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

    # Create prompts directory
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
                rules="rulebook-default",
                models="translate-default",
                symbols="aeon-core",
                glossary="aeon-core",
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
    page.insert_text((72, 120), "Body paragraph text here.", fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()


def _run_through_plan(ctx: StageContext) -> None:
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)
    NormalizeLayoutStage().execute(ctx)
    ResolveAssetsSymbolsStage().execute(ctx)
    PlanTranslationStage().execute(ctx)


class TestTranslateUnits:
    def test_translates_all_units(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway())
        stage.execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "translate_units", "summary.json", TranslationStageSummary
        )
        assert summary.status == "completed"
        assert summary.completed > 0
        assert summary.failed == 0

    def test_writes_result_files(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        plan = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "plan_translation", "translation_plan.json", TranslationPlan
        )

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway())
        stage.execute(ctx)

        for unit in plan.units:
            result = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "translate_units",
                f"results/{unit.unit_id}.json",
                TranslationResult,
            )
            assert result.unit_id == unit.unit_id
            assert len(result.translations) == len(unit.text_nodes)

    def test_handles_llm_failure(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway(fail=True))
        stage.execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "translate_units", "summary.json", TranslationStageSummary
        )
        assert summary.status == "failed"
        assert summary.failed > 0
        assert summary.completed == 0

    def test_bad_json_records_errors(self, tmp_path: Path) -> None:
        """Validation errors from bad JSON must be recorded in the error collector."""
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway(bad_json=True))
        stage.execute(ctx)

        collected = ctx.errors.collect()
        assert len(collected) > 0, "Validation errors must be recorded in the error collector"
        assert any(e.error_type == "validation_error" for e in collected)

    def test_handles_bad_json(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway(bad_json=True))
        stage.execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "translate_units", "summary.json", TranslationStageSummary
        )
        assert summary.failed > 0

    def test_translation_memory_reuse(self, tmp_path: Path) -> None:
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)
        _run_through_plan(ctx)

        # First run — populates cache
        stage1 = TranslateUnitsStage()
        stage1.set_gateway(MockGateway())
        stage1.execute(ctx)

        # Second run — should hit cache
        store2 = ArtifactStore(tmp_path / "artifacts")
        run_id2 = "run-002"
        store2.create_run(run_id2, ["test-doc"])
        ctx2 = _make_context(tmp_path, pdf, run_id=run_id2)
        # Re-run pipeline stages to populate new run's artifacts
        _run_through_plan(ctx2)

        stage2 = TranslateUnitsStage()
        stage2.set_gateway(MockGateway())
        stage2.execute(ctx2)

        summary = ctx2.artifact_store.read_artifact(
            ctx2.run_id, ctx2.doc_id, "translate_units", "summary.json", TranslationStageSummary
        )
        assert summary.cached > 0

    def test_empty_plan(self, tmp_path: Path) -> None:
        """Stage handles empty translation plan gracefully."""
        pdf = tmp_path / "source.pdf"
        _create_simple_pdf(pdf)
        ctx = _make_context(tmp_path, pdf)

        # Run up to plan stage
        _run_through_plan(ctx)

        # Overwrite plan with empty one
        empty_plan = TranslationPlan(doc_id="test-doc")
        ctx.artifact_store.write_artifact(
            ctx.run_id,
            ctx.doc_id,
            "plan_translation",
            "translation_plan.json",
            empty_plan,
        )

        stage = TranslateUnitsStage()
        stage.set_gateway(MockGateway())
        stage.execute(ctx)

        summary = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "translate_units", "summary.json", TranslationStageSummary
        )
        assert summary.status == "completed"
        assert summary.total_units == 0

    def test_stage_registration(self) -> None:
        stage = TranslateUnitsStage()
        assert stage.name == "translate_units"
        assert stage.version == "1.0.0"


class TestTranslationMemory:
    def test_store_and_lookup(self, tmp_path: Path) -> None:
        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="fp123",
        )
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="\u041f\u0440\u0438\u0432\u0435\u0442")
            ],
            source_fingerprint="fp123",
        )

        tm.store(unit, result)
        lookup = tm.lookup(unit)
        assert lookup is not None
        assert lookup.unit_id == "u1"
        assert lookup.cached is True

    def test_miss_returns_none(self, tmp_path: Path) -> None:
        from aeon_reader_pipeline.models.translation_models import TextNode

        tm = TranslationMemory(tmp_path / "tm_cache")
        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="nonexistent",
        )
        assert tm.lookup(unit) is None

    def test_has_check(self, tmp_path: Path) -> None:
        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")
        assert tm.has("fp123") is False

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="fp123",
        )
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="\u041f\u0440\u0438\u0432\u0435\u0442")
            ],
        )
        tm.store(unit, result)
        assert tm.has("fp123") is True

    def test_store_rejects_all_fallback_translations(self, tmp_path: Path) -> None:
        """Results where every translation equals source text should not be cached."""
        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[
                TextNode(inline_id="i1", source_text="Hello"),
                TextNode(inline_id="i2", source_text="World"),
            ],
            source_fingerprint="fp_fallback",
        )
        # All translations are just the source text echoed back
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="Hello"),
                TranslatedNode(inline_id="i2", ru_text="World"),
            ],
            source_fingerprint="fp_fallback",
        )

        tm.store(unit, result)
        assert tm.has("fp_fallback") is False
        assert tm.lookup(unit) is None

    def test_store_rejects_empty_translations(self, tmp_path: Path) -> None:
        """Results with no translations should not be cached."""
        from aeon_reader_pipeline.models.translation_models import TextNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="fp_empty",
        )
        result = TranslationResult(
            unit_id="u1",
            translations=[],
            source_fingerprint="fp_empty",
        )

        tm.store(unit, result)
        assert tm.has("fp_empty") is False

    def test_store_accepts_partial_translations(self, tmp_path: Path) -> None:
        """Results where at least one node is genuinely translated should be cached."""
        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[
                TextNode(inline_id="i1", source_text="Hello"),
                TextNode(inline_id="i2", source_text="World"),
            ],
            source_fingerprint="fp_partial",
        )
        # One translated, one fallback
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="Привет"),
                TranslatedNode(inline_id="i2", ru_text="World"),
            ],
            source_fingerprint="fp_partial",
        )

        tm.store(unit, result)
        assert tm.has("fp_partial") is True

    def test_store_skips_without_fingerprint(self, tmp_path: Path) -> None:
        """Units without source_fingerprint should not be cached."""
        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="",
        )
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="Привет"),
            ],
        )

        tm.store(unit, result)
        # No fingerprint → nothing stored
        assert not list(tmp_path.glob("tm_cache/*.json"))

    def test_concurrent_store_first_writer_wins(self, tmp_path: Path) -> None:
        """Multiple threads storing the same fingerprint: only first write persists."""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")
        barrier = threading.Barrier(4)

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="fp_concurrent",
        )

        results_written: list[bool] = []

        def _store_worker(worker_id: int) -> bool:
            result = TranslationResult(
                unit_id="u1",
                translations=[
                    TranslatedNode(
                        inline_id="i1",
                        ru_text=f"Привет-{worker_id}",
                    ),
                ],
                source_fingerprint="fp_concurrent",
            )
            barrier.wait()  # all threads start simultaneously
            tm.store(unit, result)
            return tm.has("fp_concurrent")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_store_worker, i) for i in range(4)]
            for f in as_completed(futures):
                results_written.append(f.result())

        # All should see the entry exists
        assert all(results_written)
        # Exactly one file should exist
        files = list((tmp_path / "tm_cache").glob("*.json"))
        assert len(files) == 1

    def test_concurrent_lookup_and_store(self, tmp_path: Path) -> None:
        """Concurrent lookups don't corrupt data while a store is in progress."""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from aeon_reader_pipeline.models.translation_models import TextNode, TranslatedNode

        tm = TranslationMemory(tmp_path / "tm_cache")

        unit = TranslationUnit(
            unit_id="u1",
            doc_id="doc",
            page_number=1,
            text_nodes=[TextNode(inline_id="i1", source_text="Hello")],
            source_fingerprint="fp_rw",
        )
        result = TranslationResult(
            unit_id="u1",
            translations=[
                TranslatedNode(inline_id="i1", ru_text="Привет"),
            ],
            source_fingerprint="fp_rw",
        )

        # Pre-store one entry
        tm.store(unit, result)

        errors: list[str] = []
        barrier = threading.Barrier(8)

        def _reader() -> None:
            barrier.wait()
            for _ in range(20):
                looked = tm.lookup(unit)
                if looked is None:
                    errors.append("lookup returned None for existing entry")
                elif looked.translations[0].ru_text != "Привет":
                    errors.append(f"corrupt data: {looked.translations[0].ru_text}")

        def _writer() -> None:
            barrier.wait()
            for _ in range(20):
                tm.store(unit, result)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for _ in range(6):
                futures.append(executor.submit(_reader))
            for _ in range(2):
                futures.append(executor.submit(_writer))
            for f in as_completed(futures):
                f.result()  # raise any exceptions

        assert not errors, f"Concurrent access errors: {errors}"
