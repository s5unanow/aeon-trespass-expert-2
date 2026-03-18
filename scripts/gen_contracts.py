#!/usr/bin/env python3
"""Generate JSON Schema + TypeScript types from Pydantic models.

Usage: uv run python scripts/gen_contracts.py

Reads Pydantic models from site_bundle_models.py and enrich_content.py,
writes JSON Schema to packages/contracts/jsonschema/ and TypeScript
interfaces to packages/contracts/typescript/src/generated/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# -- Models to export --------------------------------------------------------
from aeon_reader_pipeline.models.site_bundle_models import (
    BundleAssetEntry,
    BundleCalloutBlock,
    BundleCaptionBlock,
    BundleDividerBlock,
    BundleFigureBlock,
    BundleGlossaryRef,
    BundleHeadingBlock,
    BundleListBlock,
    BundleListItemBlock,
    BundlePage,
    BundlePageAnchor,
    BundleParagraphBlock,
    BundleSymbolRef,
    BundleTableBlock,
    BundleTextRun,
    CatalogEntry,
    CatalogManifest,
    SiteBundleManifest,
)
from aeon_reader_pipeline.stages.enrich_content import (
    NavEntry,
    NavigationTree,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
JSONSCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "jsonschema"
TS_GENERATED_DIR = REPO_ROOT / "packages" / "contracts" / "typescript" / "src" / "generated"

# Ordered list of all models to export (order matters for TS output)
EXPORT_MODELS: list[type[BaseModel]] = [
    # Inline nodes
    BundleTextRun,
    BundleSymbolRef,
    BundleGlossaryRef,
    # Block types
    BundleHeadingBlock,
    BundleParagraphBlock,
    BundleListItemBlock,
    BundleListBlock,
    BundleFigureBlock,
    BundleCaptionBlock,
    BundleTableBlock,
    BundleCalloutBlock,
    BundleDividerBlock,
    # Page types
    BundlePageAnchor,
    BundlePage,
    # Manifest types
    BundleAssetEntry,
    SiteBundleManifest,
    # Navigation
    NavEntry,
    NavigationTree,
    # Catalog
    CatalogEntry,
    CatalogManifest,
]

# Union type aliases (name -> member model names)
UNION_TYPES: dict[str, list[str]] = {
    "BundleInlineNode": ["BundleTextRun", "BundleSymbolRef", "BundleGlossaryRef"],
    "BundleBlock": [
        "BundleHeadingBlock",
        "BundleParagraphBlock",
        "BundleListBlock",
        "BundleListItemBlock",
        "BundleFigureBlock",
        "BundleCaptionBlock",
        "BundleTableBlock",
        "BundleCalloutBlock",
        "BundleDividerBlock",
    ],
}


# -- JSON Schema generation --------------------------------------------------


def generate_json_schema() -> None:
    """Write individual JSON Schema files for each exported model."""
    JSONSCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    for model in EXPORT_MODELS:
        schema = model.model_json_schema(mode="serialization")
        name = model.__name__
        _atomic_write_json(JSONSCHEMA_DIR / f"{name}.json", schema)

    print(f"  JSON Schema: {len(EXPORT_MODELS)} files → {JSONSCHEMA_DIR}")


# -- TypeScript generation ---------------------------------------------------


def _py_type_to_ts(field_info: FieldInfo, annotation: Any) -> str:  # noqa: C901, PLR0912
    """Convert a Python type annotation to a TypeScript type string."""
    origin = get_origin(annotation)

    # Handle Optional (Union[X, None])
    if origin is type(None):
        return "null"

    # list[X] → X[]
    if origin is list:
        args = get_args(annotation)
        if args:
            inner = _py_type_to_ts(field_info, args[0])
            return f"{inner}[]"
        return "unknown[]"

    # Literal["a", "b"] → "a" | "b"
    if origin is Literal:
        args = get_args(annotation)
        return " | ".join(f'"{a}"' for a in args)

    # Union types (X | Y | None)
    if isinstance(annotation, types.UnionType) or origin is Union:
        args = get_args(annotation)
        parts = [_py_type_to_ts(field_info, a) for a in args]
        return " | ".join(parts)

    # Check for Annotated (used for discriminated unions)
    if hasattr(annotation, "__metadata__"):
        # Annotated type — check if it's a known union alias first
        base_args = get_args(annotation)
        if base_args:
            base = base_args[0]
            if isinstance(base, types.UnionType) or get_origin(base) is Union:
                union_names = set()
                for a in get_args(base):
                    # Each union member may also be Annotated (with Tag)
                    if hasattr(a, "__metadata__"):
                        inner = get_args(a)[0]
                        if isinstance(inner, type):
                            union_names.add(inner.__name__)
                    elif isinstance(a, type):
                        union_names.add(a.__name__)
                # Check against known aliases
                for alias, members in UNION_TYPES.items():
                    if union_names == set(members):
                        return alias
            return _py_type_to_ts(field_info, base)

    # Pydantic model reference → use model name
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    # Basic types
    type_map: dict[type, str] = {
        str: "string",
        int: "number",
        float: "number",
        bool: "boolean",
    }
    if annotation in type_map:
        return type_map[annotation]

    # NoneType
    if annotation is type(None):
        return "null"

    return "unknown"


def _resolve_field_type(model: type[BaseModel], field_name: str) -> str:
    """Resolve a field's TypeScript type, handling union type aliases."""
    field_info = model.model_fields[field_name]
    annotation = field_info.annotation
    return _py_type_to_ts(field_info, annotation)


def _generate_interface(model: type[BaseModel]) -> str:
    """Generate a TypeScript interface for a Pydantic model."""
    lines = [f"export interface {model.__name__} {{"]

    for field_name in model.model_fields:
        ts_type = _resolve_field_type(model, field_name)
        lines.append(f"  {field_name}: {ts_type};")

    lines.append("}")
    return "\n".join(lines)


def _generate_union_type(name: str, members: list[str]) -> str:
    """Generate a TypeScript union type alias."""
    joined = " | ".join(members)
    # Single line if short enough, multi-line otherwise
    one_liner = f"export type {name} = {joined};"
    if len(one_liner) <= 100:
        return one_liner
    parts = "\n  | ".join(members)
    return f"export type {name} =\n  | {parts};"


def generate_typescript() -> None:
    """Write TypeScript interfaces to the generated directory."""
    TS_GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    sections: list[str] = [
        "/**",
        " * Public site bundle contracts — generated from Python models.",
        " *",
        " * These types mirror the Pydantic models in:",
        " *   packages/pipeline/src/aeon_reader_pipeline/models/site_bundle_models.py",
        " *",
        " * Do NOT edit manually — regenerate with `make schemas`.",
        " */",
        "",
    ]

    # Group: Inline nodes
    sections.append("// " + "-" * 75)
    sections.append("// Inline node types")
    sections.append("// " + "-" * 75)
    sections.append("")
    for model in [BundleTextRun, BundleSymbolRef, BundleGlossaryRef]:
        sections.append(_generate_interface(model))
        sections.append("")
    sections.append(_generate_union_type("BundleInlineNode", UNION_TYPES["BundleInlineNode"]))
    sections.append("")

    # Group: Block types
    sections.append("// " + "-" * 75)
    sections.append("// Block types")
    sections.append("// " + "-" * 75)
    sections.append("")
    block_models = [
        BundleHeadingBlock,
        BundleParagraphBlock,
        BundleListItemBlock,
        BundleListBlock,
        BundleFigureBlock,
        BundleCaptionBlock,
        BundleTableBlock,
        BundleCalloutBlock,
        BundleDividerBlock,
    ]
    for model in block_models:
        sections.append(_generate_interface(model))
        sections.append("")
    sections.append(_generate_union_type("BundleBlock", UNION_TYPES["BundleBlock"]))
    sections.append("")

    # Group: Page-level types
    sections.append("// " + "-" * 75)
    sections.append("// Page-level types")
    sections.append("// " + "-" * 75)
    sections.append("")
    for model in [BundlePageAnchor, BundlePage]:
        sections.append(_generate_interface(model))
        sections.append("")

    # Group: Bundle manifests
    sections.append("// " + "-" * 75)
    sections.append("// Bundle manifests")
    sections.append("// " + "-" * 75)
    sections.append("")
    for model in [BundleAssetEntry, SiteBundleManifest]:
        sections.append(_generate_interface(model))
        sections.append("")

    # Group: Navigation
    sections.append("// " + "-" * 75)
    sections.append("// Navigation")
    sections.append("// " + "-" * 75)
    sections.append("")
    for model in [NavEntry, NavigationTree]:
        sections.append(_generate_interface(model))
        sections.append("")

    # Group: Catalog
    sections.append("// " + "-" * 75)
    sections.append("// Catalog")
    sections.append("// " + "-" * 75)
    sections.append("")
    for model in [CatalogEntry, CatalogManifest]:
        sections.append(_generate_interface(model))
        sections.append("")

    content = "\n".join(sections).rstrip() + "\n"
    outpath = TS_GENERATED_DIR / "site-bundle.ts"
    _atomic_write_text(outpath, content)
    print(f"  TypeScript: {outpath}")


# -- Utilities ---------------------------------------------------------------


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically via temp file + rename."""
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically via temp file + rename."""
    fd, tmp_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# -- Main --------------------------------------------------------------------


def main() -> None:
    print("Generating contracts from Pydantic models...")
    generate_json_schema()
    generate_typescript()

    # Run TS type check to verify generated output compiles
    print("  Verifying TypeScript compiles...")
    result = subprocess.run(
        ["pnpm", "-r", "run", "typecheck"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ERROR: Generated TypeScript failed type check:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
