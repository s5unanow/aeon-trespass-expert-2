---
name: run-pipeline
description: Run the translation pipeline — full or partial runs, inspect results, sync to reader
user_invocable: true
---

# Run Pipeline

Operate the Aeon Trespass translation pipeline. Use this skill to run stages, inspect results, and sync output to the reader.

## CLI Reference

The CLI is `reader-pipeline` (installed via `uv sync`). Invoke with `uv run reader-pipeline`.

### Commands

**`run`** — Execute pipeline stages:
```bash
# Full run for one document
uv run reader-pipeline run --doc aeon-trespass-core

# Mock run (no LLM calls, no API cost)
uv run reader-pipeline run --doc aeon-trespass-core --mock

# Partial run: specific stage range
uv run reader-pipeline run --doc aeon-trespass-core --from plan_translation --to merge_localization

# Force refresh cache (re-translate everything)
uv run reader-pipeline run --doc aeon-trespass-core --cache-mode force_refresh

# Use Gemini Python SDK instead of CLI (requires GOOGLE_API_KEY)
uv run reader-pipeline run --doc aeon-trespass-core --sdk
```

| Option | Default | Description |
|--------|---------|-------------|
| `--doc` | all docs | Document ID(s), repeatable |
| `--configs` | `configs` | Config directory root |
| `--artifact-root` | `artifacts` | Artifact output root |
| `--from` | `ingest_source` | Start from this stage |
| `--to` | (last stage) | Stop after this stage |
| `--cache-mode` | `read_write` | `read_write`, `read_only`, `write_only`, `off`, `force_refresh` |
| `--strict` | `false` | Stricter validation |
| `--mock` | `false` | Mock translations (no LLM) |
| `--sdk` | `false` | Use Gemini Python SDK instead of CLI |

**`inspect`** — Check a completed run:
```bash
uv run reader-pipeline inspect {run_id} --doc aeon-trespass-core
```

**`list-stages`** — Show registered stages:
```bash
uv run reader-pipeline list-stages
```

## Environment

The default Gemini CLI gateway uses local cached credentials — no API key needed.

```bash
export GOOGLE_API_KEY="your-key"   # Only needed with --sdk flag
```

## Stage Names (exact values for --from / --to)

```
resolve_run              # 00 — Load + validate configs
ingest_source            # 01 — Load PDF
extract_primitives       # 02 — Extract text, images, tables
normalize_layout         # 03 — Normalize structure, filter noise
resolve_assets_symbols   # 04 — Resolve symbol pack
plan_translation         # 05 — Create translation units
translate_units          # 06 — LLM translation (costs money!)
merge_localization       # 07 — Merge translations back
enrich_content           # 08 — Add metadata, glossary links
evaluate_qa              # 09 — QA checks
export_site_bundle       # 11 — Export to site bundle format
build_reader             # 12 — Build static site
index_search             # 13 — Index for search
package_release          # 14 — Final release packaging
```

## Config Files

All in `configs/`:

| Path | Purpose |
|------|---------|
| `catalog.yaml` | Master list of documents and groups |
| `documents/{doc_id}.yaml` | Per-document config (PDF path, profiles, locales) |
| `model-profiles/{id}.yaml` | LLM provider, model, temperature, retries |
| `rule-profiles/{id}.yaml` | Text extraction rules (heading detection, limits) |
| `glossary-packs/{id}.yaml` | Locked terminology with translations |
| `symbol-packs/{id}.yaml` | Game symbol definitions |
| `overrides/{id}.yaml` | Page/block-level patches |

Each document config references profiles by ID:
```yaml
profiles:
  rules: rulebook-default
  models: translate-default
  symbols: aeon-core
  glossary: aeon-core
  patches: aeon-trespass-core
```

## Artifacts Structure

```
artifacts/
├── runs/{run_id}/
│   ├── run_manifest.json              # Overall run status
│   └── {doc_id}/
│       ├── 00_resolve/                # Stage output dirs
│       ├── 01_ingest/
│       ├── ...
│       └── 11_export/
│           └── site_bundle/{doc_id}/  # ← This is what gets synced to reader
├── cache/
│   └── translate_units/{fingerprint}.json  # Translation memory cache
└── state/                             # Reserved
```

Run IDs are ISO 8601 timestamps: `2024-12-18T150320Z`

## Syncing Output to Reader

After a successful run through stage 11 (export_site_bundle):

```bash
uv run python scripts/sync_generated_bundle.py \
    --artifacts-root artifacts \
    --run {run_id} \
    --doc aeon-trespass-core \
    --target apps/reader/generated
```

Then build the reader:
```bash
pnpm --filter reader build
```

## Common Workflows

### Full end-to-end (costs money)
```bash
export GOOGLE_API_KEY="..."
uv run reader-pipeline run --doc aeon-trespass-core
# Note the run_id from output
uv run python scripts/sync_generated_bundle.py --run {run_id} --doc aeon-trespass-core
pnpm --filter reader build
```

### Re-translate only (reuses extraction + normalization)
```bash
uv run reader-pipeline run --doc aeon-trespass-core --from plan_translation --to merge_localization
```

### Test pipeline changes without LLM costs
```bash
uv run reader-pipeline run --doc aeon-trespass-core --mock
```

### Re-export and rebuild site (no LLM)
```bash
uv run reader-pipeline run --doc aeon-trespass-core --from export_site_bundle
uv run python scripts/sync_generated_bundle.py --run {run_id} --doc aeon-trespass-core
pnpm --filter reader build
```

## Read gotchas.md before running the pipeline.
