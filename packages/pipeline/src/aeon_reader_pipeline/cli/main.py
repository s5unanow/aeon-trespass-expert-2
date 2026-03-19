"""CLI entry point for the Aeon Reader Pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import typer

if TYPE_CHECKING:
    from aeon_reader_pipeline.llm.base import LlmGateway
    from aeon_reader_pipeline.models.config_models import ModelProfile
    from aeon_reader_pipeline.models.run_models import CostEstimate, PipelineConfig
    from aeon_reader_pipeline.stage_framework.context import StageContext

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
    cli: bool,
    dry_run: bool,
    pipeline_config: PipelineConfig,
) -> tuple[PipelineConfig, LlmGateway | None]:
    """Configure the LLM gateway and return (pipeline_config, gateway).

    Returns a (possibly updated) pipeline_config to allow concurrency changes,
    and the gateway instance (or None for dry-run).
    """
    from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse

    llm_gateway: LlmGateway | None = None
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

        llm_gateway = _MockGateway()
        typer.echo("Using mock translation gateway.")
    elif cli:
        from aeon_reader_pipeline.llm.gemini_cli import GeminiCliGateway

        llm_gateway = GeminiCliGateway()
        pipeline_config = pipeline_config.model_copy(update={"llm_concurrency": 1})
        typer.echo("Using Gemini CLI gateway (concurrency=1).")
    elif not dry_run:
        from aeon_reader_pipeline.llm.gemini import GeminiProvider

        llm_gateway = GeminiProvider()

    return pipeline_config, llm_gateway


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
    cli: bool = typer.Option(False, help="Use Gemini CLI instead of SDK (no API key needed)"),
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
) -> None:
    """Execute a pipeline run."""
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
    )

    # Set up translation gateway
    if source_only:
        llm_gateway = None
    else:
        pipeline_config, llm_gateway = _setup_gateway(
            mock=mock,
            cli=cli,
            dry_run=dry_run,
            pipeline_config=pipeline_config,
        )

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


if __name__ == "__main__":
    app()
