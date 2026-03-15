"""CLI entry point for the Aeon Reader Pipeline."""

import typer

app = typer.Typer(
    name="reader-pipeline",
    help="Aeon Trespass Reader Pipeline — content compiler for rulebook translation.",
    no_args_is_help=True,
)


@app.command()
def list_stages() -> None:
    """List all registered pipeline stages."""
    typer.echo("Pipeline stages: (not yet registered)")


@app.command()
def run() -> None:
    """Execute a pipeline run."""
    typer.echo("Pipeline run: (not yet implemented)")


if __name__ == "__main__":
    app()
