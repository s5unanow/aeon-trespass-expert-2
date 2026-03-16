# CLAUDE.md — Aeon Trespass Expert

## What this is

Content compiler + static reader for Aeon Trespass rulebook translation (EN→RU).
Monorepo with two products:

- **packages/pipeline** — Python 3.12 content compiler (PDF → IR → translate → QA → site bundle)
- **apps/reader** — Next.js 15 static reader that renders the bundle

## Repo layout

```
packages/pipeline/   Python pipeline (uv, pydantic, orjson, typer, structlog)
packages/contracts/  Generated JSON Schema + TS types (source of truth: Python models)
apps/reader/         Next.js 15 / React 19 static site (pnpm, CSS Modules)
configs/             YAML configs: documents, rule-profiles, model-profiles, glossary/symbol packs
docs/                Architecture docs (read on demand, not memorized)
tests/backend/       pytest test suite
artifacts/           Pipeline output (gitignored run data)
prompts/             LLM prompt templates
```

## Commands

```bash
make bootstrap        # Install all deps (uv sync + pnpm install)
make lint             # ruff check + ruff format --check + pnpm lint
make typecheck        # mypy (strict) + tsc
make test             # All tests
make test-backend     # pytest only
make site-build       # Next.js static export
make schemas          # Regenerate contracts from Pydantic models
```

## Quality gates (must pass before commit)

1. `ruff check` — no lint errors
2. `ruff format --check` — no format violations
3. `mypy --strict` — no type errors (72+ source files)
4. `pytest` — all tests pass
5. `tsc` — frontend type check (contracts + reader)

CI runs gates 1-5 on every push. **Always run `make lint` before committing.**

## Conventions

- **Commit prefixes**: `EP-XXX:` for epic work (EP-001, EP-002, etc.)
- **Contract direction**: Python Pydantic → JSON Schema → TypeScript (never manual TS types)
- **JSON IO**: Always use orjson with atomic writes (temp + rename)
- **Config hashing**: Deterministic SHA-256 for cache keys and reproducibility
- **Stage names**: 15-stage canonical order defined in `stage_framework/registry.py`

## Architecture (read docs/ for detail)

- `docs/PROJECT_ARCHITECTURE.md` — full system design
- `docs/PROJECT_ARCHITECTURE_TO_AGENTIC.md` — implementation assumptions and locked decisions

Key principles:
- Canonical IR first (not markdown). Typed contracts at every stage boundary.
- Deterministic structure, bounded LLM semantics (LLMs translate text only).
- Immutable runs, resumable work units, content-addressed caching.
- Static delivery — reader is pure static output.

## Current state

- **EP-001** (done): Workspace, toolchain, scaffolding, CI, all quality gates
- **EP-002** (done): Pipeline runtime — models, config loading, artifact store, stage framework, runner, CLI
- **EP-003** (done): Source ingest and primitive extraction — DocumentManifest, ExtractedPage, raw asset extraction, golden tests
- **EP-004** (done): Canonical IR normalization and asset/symbol resolution — PageRecord, Block/InlineNode discriminated unions, normalize_layout, resolve_assets_symbols, patch/override system

## Pipeline stages (15-stage order)

```
00_resolve → 01_ingest → 02_extract → 03_normalize → 04_resolve_assets →
05_plan_translation → 06_translate → 07_merge → 08_enrich → 09_evaluate_qa →
10_fix → 11_export → 12_build → 13_index → 14_release
```

Stage implementations go in `packages/pipeline/src/aeon_reader_pipeline/stages/`.
