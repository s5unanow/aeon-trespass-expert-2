"""CLI entry point for the Aeon Reader Pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from aeon_reader_pipeline.stage_framework.registry import (
    get_all_stages_ordered,
    get_registered_stages,
)

app = typer.Typer(
    name="reader-pipeline",
    help="Aeon Trespass Reader Pipeline — content compiler for rulebook translation.",
    no_args_is_help=True,
)


@app.command()
def list_stages() -> None:
    """List all pipeline stages and their registration status."""
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
) -> None:
    """Execute a pipeline run."""
    _ = strict  # reserved for future use
    run_id = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    typer.echo(f"Run {run_id}: docs={doc}, from={from_stage}, to={to_stage}")
    typer.echo(f"Config root: {configs}, artifact root: {artifact_root}")
    typer.echo(f"Cache mode: {cache_mode}")
    typer.echo("Pipeline execution not yet connected — stages must be registered first.")


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
