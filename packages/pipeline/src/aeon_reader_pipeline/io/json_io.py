"""Safe JSON and JSONL reading/writing with orjson."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel


def write_json(path: Path, model: BaseModel) -> None:
    """Atomically write a Pydantic model as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = orjson.dumps(
        model.model_dump(mode="json"),
        option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
    )
    _atomic_write(path, data)


def read_json[T: BaseModel](path: Path, model_cls: type[T]) -> T:
    """Read and validate a JSON file into a Pydantic model."""
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    raw = path.read_bytes()
    data = orjson.loads(raw)
    return model_cls.model_validate(data)


def write_jsonl(path: Path, models: list[BaseModel]) -> None:
    """Atomically write a list of Pydantic models as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[bytes] = []
    for model in models:
        line = orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
        lines.append(line)
    data = b"\n".join(lines) + b"\n" if lines else b""
    _atomic_write(path, data)


def append_jsonl(path: Path, model: BaseModel) -> None:
    """Append a single Pydantic model to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = orjson.dumps(model.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)
    with open(path, "ab") as f:
        f.write(line + b"\n")


def read_jsonl[T: BaseModel](path: Path, model_cls: type[T]) -> list[T]:
    """Read and validate a JSONL file into a list of Pydantic models."""
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    results: list[T] = []
    with open(path, "rb") as f:
        for line_bytes in f:
            line = line_bytes.strip()
            if not line:
                continue
            data = orjson.loads(line)
            results.append(model_cls.model_validate(data))
    return results


def write_raw_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    """Atomically write raw dict/list as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    _atomic_write(path, encoded)


def read_raw_json(path: Path) -> dict[str, Any] | list[Any]:
    """Read a raw JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    result: dict[str, Any] | list[Any] = orjson.loads(path.read_bytes())
    return result


def _atomic_write(path: Path, data: bytes) -> None:
    """Write data atomically via temp file + rename."""
    fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp_path_str)
    try:
        tmp_path.write_bytes(data)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
