# ADR-001: Contract Scope and Generation Direction

**Status:** Accepted
**Date:** 2026-03-19

## Context

The architecture docs define a contract flow: Python (Pydantic) → JSON Schema → TypeScript. The `packages/contracts/` package holds the generated schemas and types consumed by the reader frontend.

An audit identified two questions:
1. Should `packages/contracts` cover **all** pipeline models (config, run, stage manifests, translation units) or only **reader-facing** public types?
2. Is the generation direction actually enforced, or does the TypeScript generator bypass JSON Schema?

## Decision

### Scope: reader-facing public types only

`packages/contracts` publishes only the types the reader app needs at build or runtime:
- Site bundle page/block/inline-node types
- Bundle manifest, glossary, navigation, catalog
- Union type aliases (BundleBlock, BundleInlineNode)

Internal pipeline types (ModelProfile, RuleProfile, RunManifest, StageManifest, TranslationUnit, TranslationResult, ReleaseManifest) are **not** part of the public contract surface. They live in the Python model layer and do not require TypeScript representations.

### Direction: JSON Schema is the TypeScript source of truth

`scripts/gen_contracts.py` operates in two phases:
1. **Phase 1** (Python → JSON Schema): imports Pydantic models, writes individual `.json` schema files.
2. **Phase 2** (JSON Schema → TypeScript): reads `.json` files from disk, converts to TypeScript interfaces. This phase never imports pipeline model classes.

CI enforces that generated files stay in sync via `make check-generated`.

## Consequences

- Adding a new reader-facing type requires: (1) define the Pydantic model, (2) add it to the export list in `gen_contracts.py`, (3) run `make schemas`.
- Internal pipeline types can evolve freely without touching the contracts package.
- TypeScript consumers always derive from JSON Schema, preventing drift between schema and types.
