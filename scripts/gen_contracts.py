#!/usr/bin/env python3
"""Generate JSON Schema + TypeScript types from Pydantic models.

Contract flow: Python (Pydantic) → JSON Schema → TypeScript.

Phase 1 imports Python models to generate JSON Schema files.
Phase 2 reads those JSON Schema files to generate TypeScript — it never
touches pipeline model classes, ensuring JSON Schema is the single
source of truth for TypeScript types.

Usage: uv run python scripts/gen_contracts.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from aeon_reader_pipeline.models.config_models import (
    CatalogConfig,
    DocumentConfig,
    GlossaryPack,
    ModelProfile,
    PatchSet,
    RuleProfile,
    SymbolPack,
)
from aeon_reader_pipeline.models.enrich_models import (
    DocumentSummary,
    NavEntry,
    NavigationTree,
    SearchDocument,
    SearchIndex,
)
from aeon_reader_pipeline.models.evidence_models import (
    CanonicalPageEvidence,
    DocumentFurnitureProfile,
    PrimitivePageEvidence,
    ResolvedPageIR,
)
from aeon_reader_pipeline.models.extract_models import ExtractedPage
from aeon_reader_pipeline.models.ir_models import PageRecord
from aeon_reader_pipeline.models.manifest_models import DocumentManifest
from aeon_reader_pipeline.models.qa_models import QAIssue, QASummary
from aeon_reader_pipeline.models.release_models import ReleaseManifest
from aeon_reader_pipeline.models.run_models import (
    PipelineConfig,
    ResolvedRunPlan,
    RunManifest,
    StageManifest,
)
from aeon_reader_pipeline.models.translation_models import (
    TranslationPlan,
    TranslationResult,
    TranslationUnit,
)
from aeon_reader_pipeline.models.site_bundle_models import (
    BundleAssetEntry,
    BundleCalloutBlock,
    BundleCaptionBlock,
    BundleDividerBlock,
    BundleFigureBlock,
    BundleGlossary,
    BundleGlossaryEntry,
    BundleGlossaryRef,
    BundleHeadingBlock,
    BundleListBlock,
    BundleListItemBlock,
    BundlePage,
    BundlePageAnchor,
    BundleParagraphBlock,
    BundleSymbolRef,
    BundleTableBlock,
    BundleTableCell,
    BundleTextRun,
    CatalogEntry,
    CatalogManifest,
    SiteBundleManifest,
)

# ── Paths ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
JSONSCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "jsonschema"
INTERNAL_SCHEMA_DIR = JSONSCHEMA_DIR / "pipeline"
TS_GENERATED_DIR = REPO_ROOT / "packages" / "contracts" / "typescript" / "src" / "generated"

# ── Contract spec ─────────────────────────────────────────────────────
# Defines export order, union aliases, and TypeScript section groupings.
# Type information comes from JSON Schema files; these constants control
# only the structure and layout of the generated output.

# Phase 1 only: Python model objects for JSON Schema generation
_EXPORT_MODELS: list[type[BaseModel]] = [
    BundleTextRun,
    BundleSymbolRef,
    BundleGlossaryRef,
    BundleHeadingBlock,
    BundleParagraphBlock,
    BundleListItemBlock,
    BundleListBlock,
    BundleFigureBlock,
    BundleCaptionBlock,
    BundleTableCell,
    BundleTableBlock,
    BundleCalloutBlock,
    BundleDividerBlock,
    BundlePageAnchor,
    BundlePage,
    BundleAssetEntry,
    SiteBundleManifest,
    BundleGlossaryEntry,
    BundleGlossary,
    NavEntry,
    NavigationTree,
    CatalogEntry,
    CatalogManifest,
]

# Phase 1 only: internal pipeline models for JSON Schema generation.
# These get JSON Schema files but NOT TypeScript types — they live under
# packages/contracts/jsonschema/pipeline/ and are consumed only by
# Python-side schema validation and tests.
_INTERNAL_SCHEMA_MODELS: list[type[BaseModel]] = [
    # Config contracts
    DocumentConfig,
    ModelProfile,
    RuleProfile,
    SymbolPack,
    GlossaryPack,
    PatchSet,
    CatalogConfig,
    # Run/orchestration contracts
    PipelineConfig,
    ResolvedRunPlan,
    RunManifest,
    StageManifest,
    # Ingest/extract contracts
    DocumentManifest,
    ExtractedPage,
    # Evidence layer (Architecture 3)
    PrimitivePageEvidence,
    CanonicalPageEvidence,
    ResolvedPageIR,
    DocumentFurnitureProfile,
    # Semantic IR
    PageRecord,
    # Translation contracts
    TranslationUnit,
    TranslationResult,
    TranslationPlan,
    # QA contracts
    QAIssue,
    QASummary,
    # Enrich contracts (not already in public exports)
    SearchDocument,
    SearchIndex,
    DocumentSummary,
    # Release
    ReleaseManifest,
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

# TypeScript output sections: (header, model_names, union_aliases_after)
_TS_SECTIONS: list[tuple[str, list[str], list[str]]] = [
    (
        "Inline node types",
        ["BundleTextRun", "BundleSymbolRef", "BundleGlossaryRef"],
        ["BundleInlineNode"],
    ),
    (
        "Block types",
        [
            "BundleHeadingBlock",
            "BundleParagraphBlock",
            "BundleListItemBlock",
            "BundleListBlock",
            "BundleFigureBlock",
            "BundleCaptionBlock",
            "BundleTableCell",
            "BundleTableBlock",
            "BundleCalloutBlock",
            "BundleDividerBlock",
        ],
        ["BundleBlock"],
    ),
    ("Page-level types", ["BundlePageAnchor", "BundlePage"], []),
    ("Bundle manifests", ["BundleAssetEntry", "SiteBundleManifest"], []),
    ("Glossary", ["BundleGlossaryEntry", "BundleGlossary"], []),
    ("Navigation", ["NavEntry", "NavigationTree"], []),
    ("Catalog", ["CatalogEntry", "CatalogManifest"], []),
]


# ── Phase 1: Python → JSON Schema ────────────────────────────────────


def generate_json_schema() -> None:
    """Write individual JSON Schema files for each exported model."""
    JSONSCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    INTERNAL_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    for model in _EXPORT_MODELS:
        schema = model.model_json_schema(mode="serialization")
        name = model.__name__
        _atomic_write_json(JSONSCHEMA_DIR / f"{name}.json", schema)

    for model in _INTERNAL_SCHEMA_MODELS:
        schema = model.model_json_schema(mode="serialization")
        name = model.__name__
        _atomic_write_json(INTERNAL_SCHEMA_DIR / f"{name}.json", schema)

    total = len(_EXPORT_MODELS) + len(_INTERNAL_SCHEMA_MODELS)
    print(f"  JSON Schema: {len(_EXPORT_MODELS)} public → {JSONSCHEMA_DIR}")
    print(f"  JSON Schema: {len(_INTERNAL_SCHEMA_MODELS)} internal → {INTERNAL_SCHEMA_DIR}")
    print(f"  JSON Schema: {total} total")


# ── Phase 2: JSON Schema → TypeScript ────────────────────────────────
# This section reads .json files from disk only.  No pipeline model
# classes are referenced.


def _load_schema(name: str) -> dict[str, Any]:
    """Load a JSON Schema file by model name."""
    path = JSONSCHEMA_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_top_level(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (properties, $defs) from a schema.

    Some schemas (e.g. NavEntry) use a top-level ``$ref`` into ``$defs``
    for recursive types, so we need to dereference first.
    """
    defs = schema.get("$defs", {})

    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        resolved = defs.get(ref_name, {})
        return resolved.get("properties", {}), defs

    return schema.get("properties", {}), defs


def _schema_type_to_ts(  # noqa: C901, PLR0912
    prop: dict[str, Any],
    defs: dict[str, Any],
    known_models: set[str],
    _visited: frozenset[str] | None = None,
) -> str:
    """Convert a JSON Schema property definition to a TypeScript type."""
    if _visited is None:
        _visited = frozenset()

    # $ref — model reference or inline definition
    if "$ref" in prop:
        ref_name = prop["$ref"].split("/")[-1]
        if ref_name in known_models:
            return ref_name
        if ref_name in defs and ref_name not in _visited:
            return _schema_type_to_ts(defs[ref_name], defs, known_models, _visited | {ref_name})
        return "unknown"

    # const literal
    if "const" in prop:
        val = prop["const"]
        return f'"{val}"' if isinstance(val, str) else str(val)

    # enum — string union
    if "enum" in prop:
        return " | ".join(f'"{v}"' for v in prop["enum"])

    # anyOf — Union / Optional
    if "anyOf" in prop:
        parts = [_schema_type_to_ts(a, defs, known_models, _visited) for a in prop["anyOf"]]
        return " | ".join(parts)

    # oneOf — discriminated union
    if "oneOf" in prop:
        ref_names = {item["$ref"].split("/")[-1] for item in prop["oneOf"] if "$ref" in item}
        for alias, members in UNION_TYPES.items():
            if ref_names == set(members):
                return alias
        parts = [_schema_type_to_ts(a, defs, known_models, _visited) for a in prop["oneOf"]]
        return " | ".join(parts)

    # Primitive / array types
    type_val = prop.get("type")
    if type_val == "string":
        return "string"
    if type_val in ("integer", "number"):
        return "number"
    if type_val == "boolean":
        return "boolean"
    if type_val == "null":
        return "null"
    if type_val == "array":
        items = prop.get("items", {})
        inner = _schema_type_to_ts(items, defs, known_models, _visited)
        return f"{inner}[]"

    return "unknown"


def _generate_interface_from_schema(name: str, known_models: set[str]) -> str:
    """Generate a TypeScript interface by reading a JSON Schema file."""
    schema = _load_schema(name)
    properties, defs = _resolve_top_level(schema)

    lines = [f"export interface {name} {{"]
    for field_name, field_schema in properties.items():
        ts_type = _schema_type_to_ts(field_schema, defs, known_models)
        lines.append(f"  {field_name}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _generate_union_type(name: str, members: list[str]) -> str:
    """Generate a TypeScript union type alias."""
    joined = " | ".join(members)
    one_liner = f"export type {name} = {joined};"
    if len(one_liner) <= 100:
        return one_liner
    parts = "\n  | ".join(members)
    return f"export type {name} =\n  | {parts};"


def generate_typescript() -> None:
    """Write TypeScript interfaces from checked-in JSON Schema files."""
    TS_GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    known_models: set[str] = set()
    for _header, model_names, _unions in _TS_SECTIONS:
        known_models.update(model_names)

    sections: list[str] = [
        "/**",
        " * Public site bundle contracts — generated from JSON Schema.",
        " *",
        " * Source of truth: packages/contracts/jsonschema/*.json",
        " * Contract flow: Python (Pydantic) → JSON Schema → TypeScript.",
        " *",
        " * Do NOT edit manually — regenerate with `make schemas`.",
        " */",
        "",
    ]

    for header, model_names, union_names in _TS_SECTIONS:
        sections.append("// " + "-" * 75)
        sections.append(f"// {header}")
        sections.append("// " + "-" * 75)
        sections.append("")

        for model_name in model_names:
            sections.append(_generate_interface_from_schema(model_name, known_models))
            sections.append("")

        for union_name in union_names:
            sections.append(_generate_union_type(union_name, UNION_TYPES[union_name]))
            sections.append("")

    content = "\n".join(sections).rstrip() + "\n"
    outpath = TS_GENERATED_DIR / "site-bundle.ts"
    _atomic_write_text(outpath, content)
    print(f"  TypeScript: {outpath}")


# ── Utilities ─────────────────────────────────────────────────────────


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


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    print("Generating contracts from Pydantic models...")
    print("  Phase 1: Python → JSON Schema")
    generate_json_schema()
    print("  Phase 2: JSON Schema → TypeScript")
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
