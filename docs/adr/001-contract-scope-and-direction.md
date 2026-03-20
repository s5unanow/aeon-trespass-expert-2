# ADR-001: Contract Scope and Generation Direction

**Status:** Accepted (updated 2026-03-20)
**Date:** 2026-03-19

## Context

The architecture docs define a contract flow: Python (Pydantic) → JSON Schema → TypeScript. The `packages/contracts/` package holds the generated schemas and types consumed by the reader frontend.

An audit identified two questions:
1. Should `packages/contracts` cover **all** pipeline models (config, run, stage manifests, translation units) or only **reader-facing** public types?
2. Is the generation direction actually enforced, or does the TypeScript generator bypass JSON Schema?

A follow-up review (S5U-216) found that the architecture doc (`PROJECT_ARCHITECTURE_TO_AGENTIC.md`) requires first-class JSON Schema for all pipeline contracts, not just reader-facing ones. The original decision to limit JSON Schema to public types left internal contracts without checked-in schemas, preventing schema validation in tests and allowing silent contract drift.

## Decision

### JSON Schema scope: all architecture-defined contracts

JSON Schema is generated for **all** contracts listed in the architecture doc's contract table:

- **Public reader types** (`packages/contracts/jsonschema/`): site bundle pages, blocks, inline nodes, manifest, glossary, navigation, catalog. These also get TypeScript type generation.
- **Internal pipeline types** (`packages/contracts/jsonschema/pipeline/`): config models (DocumentConfig, ModelProfile, RuleProfile, SymbolPack, GlossaryPack, PatchSet, CatalogConfig), run models (PipelineConfig, ResolvedRunPlan, RunManifest, StageManifest), extraction (DocumentManifest, ExtractedPage), semantic IR (PageRecord), translation (TranslationUnit, TranslationResult, TranslationPlan), QA (QAIssue, QASummary), enrich (SearchDocument, SearchIndex, DocumentSummary), and release (ReleaseManifest). These do **not** get TypeScript types.

### TypeScript scope: reader-facing public types only

TypeScript interfaces are generated only for the public reader types. Internal pipeline types do not need TypeScript representations — they are consumed only by the Python pipeline.

### Direction: JSON Schema is the TypeScript source of truth

`scripts/gen_contracts.py` operates in two phases:
1. **Phase 1** (Python → JSON Schema): imports Pydantic models, writes `.json` schema files for both public and internal models.
2. **Phase 2** (JSON Schema → TypeScript): reads public `.json` files from disk, converts to TypeScript interfaces. This phase never imports pipeline model classes.

CI enforces that generated files stay in sync via `make check-generated`.

## Consequences

- Adding a new reader-facing type requires: (1) define the Pydantic model, (2) add it to `_EXPORT_MODELS` in `gen_contracts.py`, (3) run `make schemas`.
- Adding a new internal contract requires: (1) define the Pydantic model, (2) add it to `_INTERNAL_SCHEMA_MODELS` in `gen_contracts.py`, (3) run `make schemas`.
- Internal pipeline contract changes are now visible in git diffs via their JSON Schema files.
- Schema validation tests can validate stage outputs against checked-in internal schemas.
- TypeScript consumers always derive from JSON Schema, preventing drift between schema and types.
