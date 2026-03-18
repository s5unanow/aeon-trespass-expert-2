# Pipeline Gotchas

## API Costs
- **`translate_units` (stage 06) calls Gemini API and costs real money.** The user pays per call.
- ALWAYS batch multiple fixes before re-running translation. Never re-run translation for a single small change.
- Use `--mock` for testing pipeline code changes that don't need real translations.
- Use `--from`/`--to` to avoid re-running expensive stages unnecessarily.

## Translation Memory (TM) Cache
- TM is at `artifacts/cache/translate_units/`. Each file is `{fingerprint}.json`.
- TM uses exact-match on source fingerprint (SHA-256 of text nodes). Any change to source text = cache miss = new API call.
- If bad translations get cached, delete the specific `{fingerprint}.json` files or wipe `artifacts/cache/translate_units/` entirely.
- TM validates before caching: empty results and identical-to-source results are NOT cached.
- TM is thread-safe (uses `threading.Lock`).

## Stage Dependencies
Not all stages can be re-run independently:

| If you change... | Re-run from... | Why |
|-------------------|----------------|-----|
| PDF or extraction logic | `ingest_source` | Downstream stages depend on extracted primitives |
| Normalization rules | `normalize_layout` | Translation plan depends on normalized blocks |
| Glossary terms | `plan_translation` | Translation units embed glossary hints |
| Translation prompts | `translate_units` | Only affects LLM output |
| Merge/enrich logic | `merge_localization` | Post-translation processing |
| Export format | `export_site_bundle` | Only affects bundle shape |
| Reader code | No pipeline re-run needed | Just `pnpm --filter reader build` |

## Config Hashing
- Configs are hashed (SHA-256 via `orjson` with sorted keys) for cache keys.
- Changing a glossary pack invalidates the translation plan cache.
- Changing model profile does NOT invalidate TM (TM keys are source text, not model).

## Artifacts
- Each run gets a unique ID (ISO 8601 timestamp). Runs are immutable — never edit artifacts in place.
- Stage output directories use numeric prefixes: `00_resolve`, `01_ingest`, ..., `14_release`.
- The site bundle lives at `{run}/{doc_id}/11_export/site_bundle/{doc_id}/`.

## Common Failures
- **`GOOGLE_API_KEY` not set** → Gemini provider raises immediately. Set it or use `--mock`/`--cli`.
- **Rate limiting (429)** → Built-in retry with exponential backoff handles this. If persistent, reduce concurrency or wait.
- **PDF not found** → Check `source_pdf` path in document config. It's relative to CWD.
- **Stage already completed** → Pipeline skips it. Use `--cache-mode force_refresh` to re-run.
- **resolve_run stage empty** → Stage 00 is not fully implemented yet (S5U-127). Pipeline starts from `ingest_source` by default, which is fine.
