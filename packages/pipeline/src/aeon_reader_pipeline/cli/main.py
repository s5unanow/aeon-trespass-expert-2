"""CLI entry point for the Aeon Reader Pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import structlog
import typer

if TYPE_CHECKING:
    import pymupdf

    from aeon_reader_pipeline.io.artifact_store import ArtifactStore
    from aeon_reader_pipeline.llm.base import LlmGateway
    from aeon_reader_pipeline.models.config_models import ModelProfile
    from aeon_reader_pipeline.models.run_models import CostEstimate, PipelineConfig
    from aeon_reader_pipeline.stage_framework.context import StageContext
    from aeon_reader_pipeline.utils.architecture_compare import PageComparisonResult

logger = structlog.get_logger()

app = typer.Typer(
    name="reader-pipeline",
    help="Aeon Trespass Reader Pipeline — content compiler for rulebook translation.",
    no_args_is_help=True,
)


def _import_stages() -> None:
    """Import all stages to trigger registration."""
    import aeon_reader_pipeline.stages  # noqa: F401


def _setup_gateway(
    *,
    mock: bool,
    dry_run: bool,
) -> LlmGateway | None:
    """Configure and return the LLM gateway (or None for dry-run)."""
    from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse

    if mock:

        class _MockGateway(LlmGateway):
            def translate(
                self, system_prompt: str, user_prompt: str, model_profile: ModelProfile
            ) -> LlmResponse:
                import json as _json

                data = _json.loads(user_prompt)
                translations = [
                    {"inline_id": n["inline_id"], "ru_text": f"[RU] {n['source_text']}"}
                    for n in data["text_nodes"]
                ]
                return LlmResponse(
                    text=_json.dumps({"unit_id": data["unit_id"], "translations": translations}),
                    provider="mock",
                    model="mock",
                )

            def provider_name(self) -> str:
                return "mock"

        typer.echo("Using mock translation gateway.")
        return _MockGateway()

    if not dry_run:
        from aeon_reader_pipeline.llm.gemini_cli import GeminiCliGateway

        typer.echo("Using Gemini CLI gateway.")
        return GeminiCliGateway()

    return None


@app.command()
def list_stages() -> None:
    """List all pipeline stages and their registration status."""
    _import_stages()
    from aeon_reader_pipeline.stage_framework.registry import (
        get_all_stages_ordered,
        get_registered_stages,
    )

    all_stages = get_all_stages_ordered()
    registered = set(get_registered_stages())
    for name in all_stages:
        status = "registered" if name in registered else "not registered"
        typer.echo(f"  {name}: {status}")


def _build_pipeline_config(  # noqa: PLR0913
    *,
    run_id: str,
    doc_ids: list[str],
    from_stage: str | None,
    to_stage: str | None,
    cache_mode: str,
    strict: bool,
    skip_qa_gate: bool,
    source_only: bool,
    dry_run: bool,
    concurrency: int,
    artifact_root: Path,
    page_filter: list[int] | None = None,
) -> PipelineConfig:
    """Build a PipelineConfig from CLI arguments."""
    from aeon_reader_pipeline.models.run_models import PipelineConfig, StageSelector

    effective_to_stage = "plan_translation" if dry_run else to_stage

    stage_exclude: list[str] | None = None
    effective_skip_qa_gate = skip_qa_gate
    if source_only:
        from aeon_reader_pipeline.stage_framework.registry import TRANSLATION_STAGES

        stage_exclude = sorted(TRANSLATION_STAGES)
        effective_skip_qa_gate = True
        typer.echo("Source-only preview mode: skipping translation stages, QA gate auto-skipped.")

    return PipelineConfig(
        run_id=run_id,
        docs=doc_ids,
        stages=StageSelector(
            from_stage=from_stage or "resolve_run",
            to_stage=effective_to_stage,
            exclude=stage_exclude,
        ),
        cache_mode=cache_mode,  # type: ignore[arg-type]
        strict_mode=strict,
        skip_qa_gate=effective_skip_qa_gate,
        source_only=source_only,
        page_filter=page_filter,
        llm_concurrency=concurrency,
        artifact_root=str(artifact_root.resolve()),
    )


def _print_run_summary(
    *,
    dry_run: bool,
    source_only: bool,
    run_id: str,
    doc_ids: list[str],
    cost_estimates: list[CostEstimate],
) -> None:
    """Print the final summary after a pipeline run."""
    if dry_run:
        from aeon_reader_pipeline.utils.cost_estimation import format_cost_report

        typer.echo(f"\n{format_cost_report(cost_estimates)}")
        typer.echo("\nDry run complete. No translation calls were made.")
    elif source_only:
        typer.echo(f"\nSource-only preview run {run_id} finished.")
        typer.echo(f"Documents: {doc_ids}")
        typer.echo("Mode: source-only (no translation, QA gate skipped)")
        typer.echo("The bundle contains English source text only.")
    else:
        typer.echo(f"\nPipeline run {run_id} finished.")


def _parse_pages_option(pages: str | None) -> list[int] | None:
    """Parse the --pages CLI option into a page filter list."""
    if pages is None:
        return None
    from aeon_reader_pipeline.utils.page_filter import parse_page_range

    try:
        page_filter = parse_page_range(pages)
    except ValueError as e:
        typer.echo(f"Error: invalid --pages value: {e}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Page filter: {page_filter}")
    return page_filter


@app.command()
def run(  # noqa: PLR0913
    doc: list[str] = typer.Option([], help="Document IDs to process"),  # noqa: B008
    configs: Path = typer.Option(Path("configs"), help="Config directory root"),  # noqa: B008
    artifact_root: Path = typer.Option(  # noqa: B008
        Path("artifacts"), help="Artifact output root"
    ),
    from_stage: str | None = typer.Option(None, "--from", help="Start from this stage"),
    to_stage: str | None = typer.Option(None, "--to", help="Stop after this stage"),
    cache_mode: str = typer.Option("read_write", help="Cache mode"),
    strict: bool = typer.Option(False, help="Enable strict mode"),
    skip_qa_gate: bool = typer.Option(
        False,
        "--skip-qa-gate",
        help="Skip QA quality gate (allow low quality)",
    ),
    mock: bool = typer.Option(False, help="Use mock translation (no LLM calls)"),
    concurrency: int = typer.Option(5, help="LLM concurrency (parallel workers)"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run through plan_translation, show cost estimate, then stop",
    ),
    source_only: bool = typer.Option(
        False,
        "--source-only",
        help="Skip translation stages and produce a source-text preview bundle",
    ),
    pages: str | None = typer.Option(
        None,
        "--pages",
        help="Page filter for preview (e.g. '15', '10-15', '1,5,8-12')",
    ),
) -> None:
    """Execute a pipeline run."""
    if source_only and dry_run:
        typer.echo("Error: --source-only and --dry-run are mutually exclusive.", err=True)
        raise typer.Exit(1)

    page_filter = _parse_pages_option(pages)
    _import_stages()

    from aeon_reader_pipeline.config.loader import (
        load_all_document_configs,
        load_document_config,
        load_glossary_pack,
        load_model_profile,
        load_patch_set,
        load_rule_profile,
        load_symbol_pack,
    )
    from aeon_reader_pipeline.io.artifact_store import ArtifactStore
    from aeon_reader_pipeline.stage_framework.context import StageContext
    from aeon_reader_pipeline.stage_framework.runner import PipelineRunner

    configs_root = configs.resolve()
    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")

    # Load document configs
    if doc:
        doc_configs = [load_document_config(configs_root, d) for d in doc]
    else:
        doc_configs = load_all_document_configs(configs_root)

    if not doc_configs:
        typer.echo("No documents found to process.", err=True)
        raise typer.Exit(1)

    doc_ids = [d.doc_id for d in doc_configs]
    typer.echo(f"Run {run_id}: processing {len(doc_ids)} document(s): {doc_ids}")

    # Create artifact store and run
    store = ArtifactStore(artifact_root.resolve())
    store.create_run(run_id, doc_ids)

    pipeline_config = _build_pipeline_config(
        run_id=run_id,
        doc_ids=doc_ids,
        from_stage=from_stage,
        to_stage=to_stage,
        cache_mode=cache_mode,
        strict=strict,
        skip_qa_gate=skip_qa_gate,
        source_only=source_only,
        dry_run=dry_run,
        concurrency=concurrency,
        artifact_root=artifact_root,
        page_filter=page_filter,
    )

    # Set up translation gateway
    llm_gateway = None if source_only else _setup_gateway(mock=mock, dry_run=dry_run)

    runner = PipelineRunner()
    cost_estimates: list[CostEstimate] = []

    for doc_config in doc_configs:
        typer.echo(f"\n--- Processing: {doc_config.doc_id} ---")

        rule_profile = load_rule_profile(configs_root, doc_config.profiles.rules)
        model_profile = load_model_profile(configs_root, doc_config.profiles.models)
        symbol_pack = load_symbol_pack(configs_root, doc_config.profiles.symbols)
        glossary_pack = load_glossary_pack(configs_root, doc_config.profiles.glossary)

        patch_set = None
        if doc_config.profiles.patches:
            try:
                patch_set = load_patch_set(configs_root, doc_config.profiles.patches)
            except FileNotFoundError:
                logger.warning("patch_set_not_found", patch_id=doc_config.profiles.patches)

        ctx = StageContext(
            run_id=run_id,
            doc_id=doc_config.doc_id,
            pipeline_config=pipeline_config,
            document_config=doc_config,
            rule_profile=rule_profile,
            model_profile=model_profile,
            symbol_pack=symbol_pack,
            glossary_pack=glossary_pack,
            patch_set=patch_set,
            artifact_store=store,
            configs_root=configs_root,
            llm_gateway=llm_gateway,
        )

        runner.run(ctx)

        if dry_run:
            estimate = _compute_cost_estimate(ctx, model_profile)
            cost_estimates.append(estimate)

        typer.echo(f"Completed: {doc_config.doc_id}")

    _print_run_summary(
        dry_run=dry_run,
        source_only=source_only,
        run_id=run_id,
        doc_ids=doc_ids,
        cost_estimates=cost_estimates,
    )


def _compute_cost_estimate(ctx: StageContext, model_profile: ModelProfile) -> CostEstimate:
    """Load the translation plan from artifacts and compute a cost estimate."""
    from aeon_reader_pipeline.models.translation_models import TranslationPlan
    from aeon_reader_pipeline.utils.cost_estimation import estimate_cost

    plan = ctx.artifact_store.read_artifact(
        ctx.run_id,
        ctx.doc_id,
        "plan_translation",
        "translation_plan.json",
        TranslationPlan,
    )
    return estimate_cost(plan.units, model_profile, ctx.doc_id)


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    doc: str = typer.Option(..., help="Document ID"),
    artifact_root: Path = typer.Option(  # noqa: B008
        Path("artifacts"), help="Artifact root"
    ),
) -> None:
    """Inspect a pipeline run's artifacts and status."""
    from aeon_reader_pipeline.io.artifact_store import ArtifactStore

    _ = doc  # reserved for future use
    store = ArtifactStore(artifact_root)
    try:
        manifest = store.load_run_manifest(run_id)
        typer.echo(f"Run: {manifest.run_id}")
        typer.echo(f"Status: {manifest.status}")
        typer.echo(f"Docs: {manifest.doc_ids}")
        for stage in manifest.stages:
            typer.echo(f"  {stage.stage_name}: {stage.status}")
    except FileNotFoundError:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(1) from None


_OVERLAY_TYPES = frozenset(
    {
        "primitives",
        "furniture",
        "regions",
        "reading_order",
        "assets",
        "symbols",
        "figure_caption",
        "confidence",
    }
)


def _generate_page_overlays(
    *,
    page: pymupdf.Page,
    page_number: int,
    overlay_types: set[str],
    store: ArtifactStore,
    run_id: str,
    doc_id: str,
    dpi: int,
) -> dict[str, bytes]:
    """Generate requested overlays for a single page.

    Returns a mapping of overlay type -> PNG bytes.
    Each overlay is rendered on a fresh copy of the page annotations.
    """
    import pymupdf as _pymupdf

    from aeon_reader_pipeline.models.evidence_models import (
        DocumentAssetRegistry,
        DocumentFurnitureProfile,
        PageReadingOrder,
        PageRegionGraph,
        PageSymbolCandidates,
        PrimitivePageEvidence,
        ResolvedPageIR,
    )
    from aeon_reader_pipeline.utils.overlays import (
        render_assets_overlay,
        render_confidence_overlay,
        render_figure_caption_overlay,
        render_furniture_overlay,
        render_primitives_overlay,
        render_reading_order_overlay,
        render_regions_overlay,
        render_symbols_overlay,
    )

    results: dict[str, bytes] = {}
    src_doc = page.parent
    page_idx = page.number

    def _fresh_page() -> _pymupdf.Page:
        """Re-open the page from the same document to avoid stacked annotations."""
        return src_doc.load_page(page_idx)  # type: ignore[no-any-return]

    if "primitives" in overlay_types:
        evidence = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_primitive.json",
            PrimitivePageEvidence,
        )
        results["primitives"] = render_primitives_overlay(_fresh_page(), evidence, dpi)

    if "furniture" in overlay_types:
        profile = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            "evidence/furniture_profile.json",
            DocumentFurnitureProfile,
        )
        results["furniture"] = render_furniture_overlay(_fresh_page(), profile, page_number, dpi)

    if "regions" in overlay_types:
        region_graph = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_regions.json",
            PageRegionGraph,
        )
        results["regions"] = render_regions_overlay(_fresh_page(), region_graph, dpi)

    if "reading_order" in overlay_types:
        region_graph = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_regions.json",
            PageRegionGraph,
        )
        reading_order = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_reading_order.json",
            PageReadingOrder,
        )
        results["reading_order"] = render_reading_order_overlay(
            _fresh_page(),
            region_graph,
            reading_order,
            dpi,
        )

    if "assets" in overlay_types:
        registry = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            "evidence/asset_registry.json",
            DocumentAssetRegistry,
        )
        results["assets"] = render_assets_overlay(_fresh_page(), registry, page_number, dpi)

    if "symbols" in overlay_types:
        sym_cands = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_symbol_candidates.json",
            PageSymbolCandidates,
        )
        results["symbols"] = render_symbols_overlay(_fresh_page(), sym_cands, dpi)

    if "figure_caption" in overlay_types:
        from aeon_reader_pipeline.models.evidence_models import PageFigureCaptionLinks

        region_graph = store.read_artifact(
            run_id,
            doc_id,
            "collect_evidence",
            f"evidence/p{page_number:04d}_regions.json",
            PageRegionGraph,
        )
        fig_links = store.read_artifact(
            run_id,
            doc_id,
            "resolve_assets_symbols",
            f"pages/p{page_number:04d}_figure_caption_links.json",
            PageFigureCaptionLinks,
        )
        results["figure_caption"] = render_figure_caption_overlay(
            _fresh_page(),
            region_graph,
            fig_links.links,
            dpi,
        )

    if "confidence" in overlay_types:
        resolved = store.read_artifact(
            run_id,
            doc_id,
            "resolve_page_ir",
            f"p{page_number:04d}.json",
            ResolvedPageIR,
        )
        results["confidence"] = render_confidence_overlay(_fresh_page(), resolved, dpi)

    return results


@app.command("generate-overlays")
def generate_overlays(
    run_id: str = typer.Argument(..., help="Run ID containing evidence artifacts"),
    doc: str = typer.Option(..., help="Document ID"),
    pdf: Path = typer.Option(..., help="Source PDF path"),  # noqa: B008
    artifact_root: Path = typer.Option(  # noqa: B008
        Path("artifacts"), help="Artifact root"
    ),
    pages: str | None = typer.Option(None, "--pages", help="Page filter (e.g. '1-5', '1,3,8')"),
    overlays: str = typer.Option(
        "primitives,regions,reading_order",
        help=f"Comma-separated overlay types: {','.join(sorted(_OVERLAY_TYPES))}",
    ),
    dpi: int = typer.Option(150, help="Render DPI"),
) -> None:
    """Generate debug overlay PNGs for evidence artifacts."""
    import pymupdf

    from aeon_reader_pipeline.io.artifact_store import ArtifactStore

    if not pdf.exists():
        typer.echo(f"Error: PDF not found: {pdf}", err=True)
        raise typer.Exit(1)

    overlay_set = {s.strip() for s in overlays.split(",")}
    unknown = overlay_set - _OVERLAY_TYPES
    if unknown:
        typer.echo(f"Error: unknown overlay types: {unknown}", err=True)
        raise typer.Exit(1)

    page_filter = _parse_pages_option(pages)
    store = ArtifactStore(artifact_root.resolve())

    written = 0
    with pymupdf.open(str(pdf)) as pdf_doc:
        total_pages = pdf_doc.page_count
        target_pages = page_filter if page_filter else list(range(1, total_pages + 1))

        for page_num in target_pages:
            if page_num < 1 or page_num > total_pages:
                typer.echo(f"  Skipping page {page_num} (out of range)")
                continue

            page = pdf_doc.load_page(page_num - 1)  # 0-indexed

            try:
                page_overlays = _generate_page_overlays(
                    page=page,
                    page_number=page_num,
                    overlay_types=overlay_set,
                    store=store,
                    run_id=run_id,
                    doc_id=doc,
                    dpi=dpi,
                )
            except FileNotFoundError as exc:
                typer.echo(f"  Page {page_num}: missing artifact — {exc}")
                continue

            for overlay_type, png_bytes in page_overlays.items():
                sub_path = f"debug/overlays/p{page_num:04d}_{overlay_type}.png"
                out = store.write_debug_bytes(run_id, doc, sub_path, png_bytes)
                written += 1
                typer.echo(f"  {out}")

    typer.echo(f"\nGenerated {written} overlay(s).")


def _run_arch_pipeline(
    *,
    arch: Literal["v2", "v3"],
    doc: str,
    artifact_root: Path,
    page_filter: list[int] | None,
    store: ArtifactStore,
    ctx_kwargs: dict[str, Any],
) -> tuple[str, list[int]]:
    """Run a pipeline for a specific architecture, return (run_id, target_pages)."""
    from aeon_reader_pipeline.models.manifest_models import DocumentManifest
    from aeon_reader_pipeline.stage_framework.runner import PipelineRunner
    from aeon_reader_pipeline.utils.page_filter import pages_to_process

    run_id = f"compare-{arch}-{datetime.now(UTC).strftime('%H%M%S')}"
    store.create_run(run_id, [doc])

    pipeline_config = _build_pipeline_config(
        run_id=run_id,
        doc_ids=[doc],
        from_stage=None,
        to_stage="normalize_layout",
        cache_mode="read_write",
        strict=False,
        skip_qa_gate=True,
        source_only=False,
        dry_run=False,
        concurrency=1,
        artifact_root=artifact_root,
        page_filter=page_filter,
    )
    pipeline_config.architecture = arch

    from aeon_reader_pipeline.stage_framework.context import StageContext

    ctx = StageContext(run_id=run_id, doc_id=doc, pipeline_config=pipeline_config, **ctx_kwargs)
    typer.echo(f"\n--- Running {arch} pipeline for {doc} ---")
    PipelineRunner().run(ctx)

    manifest = store.read_artifact(
        run_id,
        doc,
        "ingest_source",
        "document_manifest.json",
        DocumentManifest,
    )
    return run_id, pages_to_process(manifest.page_count, page_filter)


def _print_comparison_report(
    doc: str,
    page_results: list[PageComparisonResult],
) -> None:
    """Print a formatted comparison table."""
    from aeon_reader_pipeline.utils.architecture_compare import (
        build_comparison_report,
    )

    report = build_comparison_report(doc, page_results)

    typer.echo(f"\n{'=' * 80}")
    typer.echo(f"Architecture Comparison: {doc}")
    typer.echo(f"{'=' * 80}")
    typer.echo(
        f"{'Page':>6} | {'v2 blocks':>10} | {'v3 blocks':>10} | "
        f"{'delta':>6} | {'v3 route':>10} | {'confidence':>10}"
    )
    sep = f"{'─' * 6}─+─{'─' * 10}─+─{'─' * 10}─+─{'─' * 6}─+─{'─' * 10}─+─{'─' * 10}"
    typer.echo(sep)

    for p in report.pages:
        typer.echo(
            f"{p.page_number:>6} | {p.v2_block_count:>10} | {p.v3_block_count:>10} | "
            f"{p.block_count_delta:>+6} | {p.v3_render_mode:>10} | {p.v3_confidence:>10.3f}"
        )

    typer.echo(sep)
    typer.echo(
        f"{'avg':>6} | {report.avg_v2_blocks:>10.1f} | {report.avg_v3_blocks:>10.1f} | "
        f"{report.avg_block_delta:>+6.1f} | {'':>10} | {report.avg_v3_confidence:>10.3f}"
    )
    typer.echo(f"\nv3 route distribution: {dict(report.v3_route_counts)}")


@app.command("compare-architectures")
def compare_architectures(
    doc: str = typer.Option(..., help="Document ID to compare"),
    configs: Path = typer.Option(Path("configs"), help="Config directory root"),  # noqa: B008
    artifact_root: Path = typer.Option(  # noqa: B008
        Path("artifacts"), help="Artifact output root"
    ),
    mock: bool = typer.Option(True, help="Use mock translation (no LLM calls)"),
    pages: str | None = typer.Option(None, "--pages", help="Page filter (e.g. '1-5')"),
) -> None:
    """Compare v2 and v3 pipeline outputs for a document side-by-side."""
    _import_stages()

    from aeon_reader_pipeline.config.loader import (
        load_document_config,
        load_glossary_pack,
        load_model_profile,
        load_rule_profile,
        load_symbol_pack,
    )
    from aeon_reader_pipeline.io.artifact_store import ArtifactStore
    from aeon_reader_pipeline.models.ir_models import PageRecord
    from aeon_reader_pipeline.utils.architecture_compare import compare_page_outputs

    page_filter = _parse_pages_option(pages)
    configs_root = configs.resolve()
    doc_config = load_document_config(configs_root, doc)

    store = ArtifactStore(artifact_root.resolve())
    llm_gateway = _setup_gateway(mock=mock, dry_run=False)

    ctx_kwargs = {
        "document_config": doc_config,
        "rule_profile": load_rule_profile(configs_root, doc_config.profiles.rules),
        "model_profile": load_model_profile(configs_root, doc_config.profiles.models),
        "symbol_pack": load_symbol_pack(configs_root, doc_config.profiles.symbols),
        "glossary_pack": load_glossary_pack(configs_root, doc_config.profiles.glossary),
        "patch_set": None,
        "artifact_store": store,
        "configs_root": configs_root,
        "llm_gateway": llm_gateway,
    }

    v2_run_id, target_pages = _run_arch_pipeline(
        arch="v2",
        doc=doc,
        artifact_root=artifact_root,
        page_filter=page_filter,
        store=store,
        ctx_kwargs=ctx_kwargs,
    )
    v3_run_id, _ = _run_arch_pipeline(
        arch="v3",
        doc=doc,
        artifact_root=artifact_root,
        page_filter=page_filter,
        store=store,
        ctx_kwargs=ctx_kwargs,
    )

    page_results = []
    for pn in target_pages:
        v2_page = store.read_artifact(
            v2_run_id,
            doc,
            "normalize_layout",
            f"pages/p{pn:04d}.json",
            PageRecord,
        )
        v3_page = store.read_artifact(
            v3_run_id,
            doc,
            "normalize_layout",
            f"pages/p{pn:04d}.json",
            PageRecord,
        )
        v3_confidence = 1.0
        try:
            from aeon_reader_pipeline.models.evidence_models import ResolvedPageIR

            resolved = store.read_artifact(
                v3_run_id,
                doc,
                "resolve_page_ir",
                f"p{pn:04d}.json",
                ResolvedPageIR,
            )
            v3_confidence = resolved.page_confidence
        except FileNotFoundError:
            pass
        page_results.append(compare_page_outputs(v2_page, v3_page, v3_confidence=v3_confidence))

    _print_comparison_report(doc, page_results)


if __name__ == "__main__":
    app()
