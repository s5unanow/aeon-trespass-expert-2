"""CLI entry point for the Aeon Reader Pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
import typer

logger = structlog.get_logger()

app = typer.Typer(
    name="reader-pipeline",
    help="Aeon Trespass Reader Pipeline — content compiler for rulebook translation.",
    no_args_is_help=True,
)


def _import_stages() -> None:
    """Import all stages to trigger registration."""
    import aeon_reader_pipeline.stages  # noqa: F401


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


@app.command()
def run(
    doc: list[str] = typer.Option([], help="Document IDs to process"),  # noqa: B008
    configs: Path = typer.Option(Path("configs"), help="Config directory root"),  # noqa: B008
    artifact_root: Path = typer.Option(  # noqa: B008
        Path("artifacts"), help="Artifact output root"
    ),
    from_stage: str | None = typer.Option(None, "--from", help="Start from this stage"),
    to_stage: str | None = typer.Option(None, "--to", help="Stop after this stage"),
    cache_mode: str = typer.Option("read_write", help="Cache mode"),
    strict: bool = typer.Option(False, help="Enable strict mode"),
    mock: bool = typer.Option(False, help="Use mock translation (no LLM calls)"),
    cli: bool = typer.Option(False, help="Use Gemini CLI instead of SDK (no API key needed)"),
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
    from aeon_reader_pipeline.llm.base import LlmGateway, LlmResponse
    from aeon_reader_pipeline.models.config_models import ModelProfile
    from aeon_reader_pipeline.models.run_models import PipelineConfig, StageSelector
    from aeon_reader_pipeline.stage_framework.context import StageContext
    from aeon_reader_pipeline.stage_framework.runner import PipelineRunner
    from aeon_reader_pipeline.stages.translate_units import TranslateUnitsStage

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

    # Create pipeline config
    pipeline_config = PipelineConfig(
        run_id=run_id,
        docs=doc_ids,
        stages=StageSelector(
            from_stage=from_stage or "ingest_source",
            to_stage=to_stage,
        ),
        cache_mode=cache_mode,  # type: ignore[arg-type]
        strict_mode=strict,
        llm_concurrency=5,
        artifact_root=str(artifact_root.resolve()),
    )

    # Set up translation gateway at the class level so runner's new instances inherit it
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

        TranslateUnitsStage._gateway = _MockGateway()  # type: ignore[assignment]
        typer.echo("Using mock translation gateway.")
    elif cli:
        from aeon_reader_pipeline.llm.gemini_cli import GeminiCliGateway

        TranslateUnitsStage._gateway = GeminiCliGateway()  # type: ignore[assignment]
        pipeline_config = pipeline_config.model_copy(update={"llm_concurrency": 1})
        typer.echo("Using Gemini CLI gateway (concurrency=1).")
    else:
        from aeon_reader_pipeline.llm.gemini import GeminiProvider

        TranslateUnitsStage._gateway = GeminiProvider()  # type: ignore[assignment]

    runner = PipelineRunner()

    for doc_config in doc_configs:
        typer.echo(f"\n--- Processing: {doc_config.doc_id} ---")

        # Load profiles
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
        )

        runner.run(ctx)

        typer.echo(f"Completed: {doc_config.doc_id}")

    typer.echo(f"\nPipeline run {run_id} finished.")


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
