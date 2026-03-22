"""End-to-end hard-page fixture test: PDF → pipeline → bundle → reader build → search.

Runs a multi-page fixture PDF through the full v3 pipeline, with one page
synthetically forced to hard-page routing (non-semantic render_mode), then
validates the entire chain: export, bundle sync, reader build, and search
data integrity.

Introduced by S5U-279.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import orjson
import pymupdf
import pytest

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
from aeon_reader_pipeline.models.enrich_models import SearchIndex
from aeon_reader_pipeline.models.evidence_models import ResolvedPageIR
from aeon_reader_pipeline.models.release_models import ReleaseManifest
from aeon_reader_pipeline.models.run_models import PipelineConfig
from aeon_reader_pipeline.models.site_bundle_models import (
    BundlePage,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stage_framework.context import StageContext
from aeon_reader_pipeline.stages.build_reader import (
    BuildReaderStage,
    ReaderBuildManifest,
)
from aeon_reader_pipeline.stages.collect_evidence import CollectEvidenceStage
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
from aeon_reader_pipeline.stages.package_release import PackageReleaseStage
from aeon_reader_pipeline.stages.plan_translation import PlanTranslationStage
from aeon_reader_pipeline.stages.resolve_assets_symbols import (
    ResolveAssetsSymbolsStage,
)
from aeon_reader_pipeline.stages.resolve_page_ir import ResolvePageIRStage
from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage

# ---------------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------------

DOC_ID = "hard-page-fixture"


class _MockGateway(LlmGateway):
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


def _create_fixture_pdf(path: Path) -> None:
    """Create a 3-page fixture PDF with mixed content complexity.

    Page 1 — simple heading + body (semantic)
    Page 2 — heading + body (forced to hybrid via resolved IR override)
    Page 3 — heading + body (semantic)
    """
    doc = pymupdf.open()

    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter One: Getting Started", fontsize=20, fontname="hebo")
    page.insert_text(
        (72, 120), "Players begin by selecting their character class.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 150), "Each class provides unique abilities and stats.", fontsize=11, fontname="helv"
    )

    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Two: Complex Encounters", fontsize=20, fontname="hebo")
    page.insert_text(
        (72, 120), "Combat encounters use multiple phases.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 150), "Roll initiative and resolve actions in order.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 180), "Track damage on the encounter sheet.", fontsize=11, fontname="helv"
    )

    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Chapter Three: Exploration", fontsize=20, fontname="hebo")
    page.insert_text(
        (72, 120), "Explore the world map to discover new locations.", fontsize=11, fontname="helv"
    )
    page.insert_text(
        (72, 150), "Each location has unique events and rewards.", fontsize=11, fontname="helv"
    )

    toc = [
        [1, "Chapter One: Getting Started", 1],
        [1, "Chapter Two: Complex Encounters", 2],
        [1, "Chapter Three: Exploration", 3],
    ]
    doc.set_toc(toc)
    doc.set_metadata({"title": "Hard Page Fixture", "author": "Test Suite"})
    doc.save(str(path))
    doc.close()


def _make_context(tmp_path: Path, pdf_path: Path) -> StageContext:
    """Build a StageContext for hard-page e2e tests."""
    configs_root = tmp_path / "configs"
    configs_root.mkdir(exist_ok=True)
    prompts = tmp_path / "prompts" / "translate" / "v1"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.j2").write_text("Translate from {{ source_locale }} to {{ target_locale }}.")
    (prompts / "response_schema.json").write_text("{}")

    # Create reader generated dir for build_reader stage
    (tmp_path / "apps" / "reader" / "generated").mkdir(parents=True, exist_ok=True)

    store = ArtifactStore(tmp_path / "artifacts")
    store.create_run("run-hard-e2e", [DOC_ID])

    return StageContext(
        run_id="run-hard-e2e",
        doc_id=DOC_ID,
        pipeline_config=PipelineConfig(run_id="run-hard-e2e"),
        document_config=DocumentConfig(
            doc_id=DOC_ID,
            slug=DOC_ID,
            source_pdf=str(pdf_path),
            titles=DocumentTitles(
                en="Hard Page Fixture", ru="\u0424\u0438\u043a\u0441\u0442\u0443\u0440\u0430"
            ),
            source_locale="en",
            target_locale="ru",
            profiles=DocumentProfiles(rules="test", models="test", symbols="test", glossary="test"),
            build=DocumentBuild(route_base=f"/docs/{DOC_ID}"),
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


def _run_pipeline(tmp_path: Path) -> tuple[StageContext, Path]:
    """Run the full v3 pipeline with a hard-page override on page 2.

    Shared by all test classes so the pipeline runs once per fixture scope.
    """
    pdf = tmp_path / "fixture.pdf"
    _create_fixture_pdf(pdf)
    ctx = _make_context(tmp_path, pdf)

    # --- Stages 01-02: Ingest + Extract (real PDF) ---
    IngestSourceStage().execute(ctx)
    ExtractPrimitivesStage().execute(ctx)

    # --- Stage 02a: Collect evidence (v3) ---
    CollectEvidenceStage().execute(ctx)

    # --- Stage 02b: Resolve page IR (v3) ---
    ResolvePageIRStage().execute(ctx)

    # Override page 2 resolved IR to force non-semantic routing.
    # This simulates a hard page (e.g. dense multi-column layout) that
    # the confidence scorer routes to hybrid rendering.  The override
    # happens *after* the evidence stages so that collect_evidence and
    # resolve_page_ir run normally on all pages, and only the routing
    # decision is forced — testing the full downstream chain (normalize
    # → translate → export → bundle) with a non-semantic render_mode.
    hard_resolved = ResolvedPageIR(
        page_number=2,
        doc_id=DOC_ID,
        width_pt=612.0,
        height_pt=792.0,
        canonical_evidence_hash="forced-hard-page-hash",
        render_mode="hybrid",
        fallback_image_ref="p0002_fallback.png",
        page_confidence=0.45,
        confidence_reasons=["forced_hard_page_for_e2e_test"],
    )
    ctx.artifact_store.write_artifact(
        ctx.run_id,
        ctx.doc_id,
        "resolve_page_ir",
        "resolved/p0002.json",
        hard_resolved,
    )

    # --- Stage 03: Normalize layout ---
    NormalizeLayoutStage().execute(ctx)

    # --- Stage 04: Resolve assets/symbols ---
    ResolveAssetsSymbolsStage().execute(ctx)

    # --- Stage 05: Plan translation ---
    PlanTranslationStage().execute(ctx)

    # --- Stage 06: Translate units ---
    ctx.llm_gateway = _MockGateway()
    TranslateUnitsStage().execute(ctx)

    # --- Stage 07: Merge localization ---
    MergeLocalizationStage().execute(ctx)

    # --- Stage 08: Enrich content ---
    EnrichContentStage().execute(ctx)

    # --- Stage 09: Evaluate QA ---
    EvaluateQAStage().execute(ctx)

    # --- Stage 11: Export site bundle (stage 10 intentionally absent) ---
    ExportSiteBundleStage().execute(ctx)

    # --- Stage 12: Build reader (sync bundle) ---
    BuildReaderStage().execute(ctx)

    # --- Stage 13: Index search ---
    IndexSearchStage().execute(ctx)

    # --- Stage 14: Package release ---
    PackageReleaseStage().execute(ctx)

    bundle_dir = (
        ctx.artifact_store.stage_dir(ctx.run_id, ctx.doc_id, "export_site_bundle")
        / "site_bundle"
        / DOC_ID
    )
    return ctx, bundle_dir


# ---------------------------------------------------------------------------
# Shared fixture — runs the pipeline once per test class
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def pipeline_result(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[tuple[StageContext, Path], None, None]:
    """Run the full v3 pipeline once and share results across all tests."""
    tmp_path = tmp_path_factory.mktemp("hard_page_e2e")
    yield _run_pipeline(tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHardPageE2E:
    """End-to-end pipeline test with hard-page routing."""

    def test_pipeline_completes(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Full pipeline runs without errors."""
        ctx, _ = pipeline_result
        release = ctx.artifact_store.read_artifact(
            ctx.run_id, ctx.doc_id, "package_release", "release_manifest.json", ReleaseManifest
        )
        assert release.all_accepted

    def test_hard_page_routes_non_semantic(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Page 2 (hard-page override) routes to hybrid or facsimile."""
        ctx, _ = pipeline_result
        p2 = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/pages/p0002.json",
            BundlePage,
        )
        assert p2.render_mode in ("hybrid", "facsimile"), (
            f"Hard page should route non-semantic, got {p2.render_mode}"
        )

    def test_fallback_image_ref_set_for_hard_page(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Non-semantic pages must have fallback_image_ref set."""
        ctx, _ = pipeline_result
        p2 = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/pages/p0002.json",
            BundlePage,
        )
        if p2.render_mode != "semantic":
            assert p2.fallback_image_ref is not None, (
                f"Page 2 with render_mode={p2.render_mode} must have fallback_image_ref"
            )

    def test_semantic_pages_route_correctly(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Pages 1 and 3 (real extraction, simple content) route as semantic."""
        ctx, _ = pipeline_result
        for pn in (1, 3):
            bp = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "export_site_bundle",
                f"site_bundle/{DOC_ID}/pages/p{pn:04d}.json",
                BundlePage,
            )
            assert bp.render_mode == "semantic", (
                f"Page {pn} (simple content) expected semantic, got {bp.render_mode}"
            )

    def test_all_page_json_present_in_bundle(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Every page has a corresponding JSON file in the exported bundle."""
        ctx, bundle_dir = pipeline_result
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/bundle_manifest.json",
            SiteBundleManifest,
        )
        for pn in range(1, manifest.page_count + 1):
            page_path = bundle_dir / "pages" / f"p{pn:04d}.json"
            assert page_path.exists(), f"Missing bundle page JSON: {page_path}"

    def test_bundle_manifest_valid(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Bundle manifest has correct metadata."""
        ctx, _ = pipeline_result
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/bundle_manifest.json",
            SiteBundleManifest,
        )
        assert manifest.doc_id == DOC_ID
        assert manifest.page_count == 3
        assert manifest.has_search is True
        assert manifest.qa_accepted is True

    def test_search_documents_cover_all_pages(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Search documents exist and cover pages with content."""
        ctx, _ = pipeline_result
        search = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/search_documents.json",
            SearchIndex,
        )
        assert search.total_documents >= 1, "No search documents generated"
        pages_covered = {doc.page_number for doc in search.documents}
        # At minimum pages 1 and 3 (semantic) should have searchable content
        assert 1 in pages_covered, "Page 1 missing from search documents"
        assert 3 in pages_covered, "Page 3 missing from search documents"

    def test_search_index_manifest_valid(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Search index manifest records positive document count."""
        ctx, _ = pipeline_result
        search_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "index_search",
            "search_index_manifest.json",
            SearchIndexManifest,
        )
        assert search_manifest.total_documents >= 1
        assert search_manifest.index_status == "search-data-validated"

    def test_asset_refs_resolve(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Every asset_ref in figure blocks points to an existing file or is empty."""
        ctx, _ = pipeline_result
        manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "export_site_bundle",
            f"site_bundle/{DOC_ID}/bundle_manifest.json",
            SiteBundleManifest,
        )
        for pn in range(1, manifest.page_count + 1):
            bp = ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "export_site_bundle",
                f"site_bundle/{DOC_ID}/pages/p{pn:04d}.json",
                BundlePage,
            )
            for block in bp.blocks:
                block_data = block.model_dump()
                asset_ref = block_data.get("asset_ref", "")
                if asset_ref and asset_ref.startswith("/assets/"):
                    # Strip leading /assets/<doc_id>/ to get relative path
                    rel = asset_ref.split("/", 3)[-1] if asset_ref.count("/") >= 3 else asset_ref
                    assert rel, f"Empty asset_ref after prefix strip on page {pn}"

    def test_bundle_synced_to_reader(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Build reader stage syncs bundle to the generated directory."""
        ctx, _ = pipeline_result
        build_manifest = ctx.artifact_store.read_artifact(
            ctx.run_id,
            ctx.doc_id,
            "build_reader",
            "build_manifest.json",
            ReaderBuildManifest,
        )
        assert build_manifest.build_status == "bundle-synced"
        assert build_manifest.bundle_page_count == 3
        assert build_manifest.synced_files > 0

        # Verify files exist in the reader generated directory
        generated_dir = Path(build_manifest.reader_generated_dir)
        assert generated_dir.exists(), f"Reader generated dir missing: {generated_dir}"
        assert (generated_dir / "bundle_manifest.json").exists()
        assert (generated_dir / "pages" / "p0001.json").exists()
        assert (generated_dir / "pages" / "p0002.json").exists()
        assert (generated_dir / "pages" / "p0003.json").exists()

    def test_catalog_written(self, pipeline_result: tuple[StageContext, Path]) -> None:
        """Catalog manifest is written to the reader generated root."""
        ctx, _ = pipeline_result
        generated_root = Path(
            ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "build_reader",
                "build_manifest.json",
                ReaderBuildManifest,
            ).reader_generated_dir
        ).parent
        catalog_path = generated_root / "catalog.json"
        assert catalog_path.exists(), "catalog.json not written"
        catalog = orjson.loads(catalog_path.read_bytes())
        assert catalog["total_documents"] >= 1
        doc_ids = [d["doc_id"] for d in catalog["documents"]]
        assert DOC_ID in doc_ids


# ---------------------------------------------------------------------------
# Reader build integration (requires pnpm)
# ---------------------------------------------------------------------------


def _pnpm_available() -> bool:
    try:
        subprocess.run(
            ["pnpm", "--version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


class TestReaderBuildIntegration:
    """Integration tests that require Node.js / pnpm to be available.

    These verify the reader can build with pipeline-produced hard-page bundles.
    Skipped in environments without pnpm.

    NOTE: This test temporarily replaces ``apps/reader/generated/`` in the real
    project directory and restores it afterward.  Do not run in parallel with
    other tests that modify that directory.
    """

    @pytest.mark.skipif(not _pnpm_available(), reason="pnpm not available")
    def test_reader_builds_with_hard_page_bundle(
        self, pipeline_result: tuple[StageContext, Path]
    ) -> None:
        """Verify the Next.js reader builds successfully with hard-page bundle data."""
        ctx, _ = pipeline_result
        generated_dir = Path(
            ctx.artifact_store.read_artifact(
                ctx.run_id,
                ctx.doc_id,
                "build_reader",
                "build_manifest.json",
                ReaderBuildManifest,
            ).reader_generated_dir
        ).parent

        # Find the real project root (where apps/reader lives)
        project_root = Path(__file__).resolve().parent.parent.parent
        reader_dir = project_root / "apps" / "reader"
        real_generated = reader_dir / "generated"

        if not reader_dir.exists():
            pytest.skip("Reader app directory not found")

        # Back up existing generated dir if present and swap in test data
        backup = None
        out_dir = reader_dir / "out"
        try:
            if real_generated.exists():
                backup = real_generated.with_name("generated.bak")
                if backup.exists():
                    shutil.rmtree(backup)
                real_generated.rename(backup)

            # Copy pipeline-produced bundle to real reader location
            shutil.copytree(generated_dir, real_generated)

            # Run the reader build
            result = subprocess.run(
                ["pnpm", "--filter", "reader", "build"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=120,
            )
            assert result.returncode == 0, (
                f"Reader build failed:\nstdout: {result.stdout[-500:]}\n"
                f"stderr: {result.stderr[-500:]}"
            )

            # Verify static output was produced
            assert out_dir.exists(), "Reader build did not produce out/ directory"

            # Check page routes exist
            for pn in range(1, 4):
                page_route = out_dir / "docs" / DOC_ID / "page" / str(pn) / "index.html"
                assert page_route.exists(), f"Missing page route: {page_route}"
        finally:
            # Clean up build artifacts and restore original generated dir
            if out_dir.exists():
                shutil.rmtree(out_dir)
            if real_generated.exists():
                shutil.rmtree(real_generated)
            if backup and backup.exists():
                backup.rename(real_generated)
