"""Smoke tests — verify basic package imports and toolchain."""


def test_pipeline_import() -> None:
    """Pipeline package is importable."""
    import aeon_reader_pipeline

    assert hasattr(aeon_reader_pipeline, "__version__")
    assert aeon_reader_pipeline.__version__ == "0.1.0"


def test_pydantic_available() -> None:
    """Pydantic v2 is installed and importable."""
    import pydantic

    assert int(pydantic.VERSION.split(".")[0]) >= 2


def test_orjson_available() -> None:
    """orjson is installed and importable."""
    import orjson

    data = {"key": "value"}
    encoded = orjson.dumps(data)
    decoded = orjson.loads(encoded)
    assert decoded == data


def test_typer_available() -> None:
    """Typer is installed and the CLI app exists."""
    from aeon_reader_pipeline.cli.main import app

    assert app is not None
