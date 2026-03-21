# Aeon Trespass Expert

Content compiler and static reader for Aeon Trespass rulebook translation (EN → RU).

## Products

- **`packages/pipeline`** — Python 3.12 content compiler (PDF → IR → translate → QA → site bundle)
- **`apps/reader`** — Next.js 15 static reader that renders the translated bundle

## Quick start

```bash
# Install all dependencies (Python + Node)
make bootstrap

# Run quality gates
make lint && make typecheck && make test

# Start the reader dev server
make site-dev
```

## Pipeline usage

```bash
# Full pipeline run (requires Gemini API key)
reader-pipeline run --doc aeon-trespass-core

# Dry run with cost estimate (no API calls)
reader-pipeline run --doc aeon-trespass-core --dry-run

# Mock translation (no API key needed)
reader-pipeline run --doc aeon-trespass-core --mock

# List all pipeline stages
reader-pipeline list-stages
```

## Pipeline stages

```
00_resolve_run → 01_ingest_source → 02_extract_primitives → 03_normalize_layout →
04_resolve_assets_symbols → 05_plan_translation → 06_translate_units → 07_merge_localization →
08_enrich_content → 09_evaluate_qa → 11_export_site_bundle →
12_build_reader → 13_index_search → 14_package_release
```

## Development workflow

All work is tracked in Linear (project ATE2, team S5U). See [docs/operator-guides/dev-release-loop.md](docs/operator-guides/dev-release-loop.md) for the full development and release workflow.

## Quality gates

| Gate | Command | Enforced |
|------|---------|----------|
| Lint | `ruff check` + `ruff format --check` | Pre-commit + CI |
| Types (Python) | `mypy --strict` | Pre-commit + CI |
| Types (TS) | `tsc` | Pre-commit + CI |
| Tests (Python) | `pytest` | Pre-commit + CI |
| Tests (TS) | `vitest` | CI |
| Import boundaries | `uv run lint-imports` | CI |
| E2E | `pnpm --filter reader test:e2e` | CI |

## Architecture

- [docs/PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md) — Full system design
- [docs/adr/](docs/adr/) — Architecture decision records
- [docs/operator-guides/](docs/operator-guides/) — Operational guides

Key principles: canonical IR first, typed contracts at every stage boundary, deterministic structure with bounded LLM semantics, immutable runs, static delivery.
