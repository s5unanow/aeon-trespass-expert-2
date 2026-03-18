# Verify Reader Gotchas

## Port
- Always use port **3002** for the local reader server. This is the project standard.

## Playwright
- Screenshot script requires Playwright chromium. Install if missing:
  ```bash
  pnpm exec playwright install chromium
  ```
- If Playwright fails with "browser not found", the above command fixes it.

## Static Export vs Dev Server
- `pnpm --filter reader build` produces a **static export** in `apps/reader/out/`.
- Serve from `apps/reader/out/`, NOT from `.next/`.
- The dev server (`pnpm --filter reader dev`) works too but is slower and not what gets deployed.

## Bundle Must Be Synced First
- If `apps/reader/generated/` is empty or outdated, the build will succeed but pages will be blank.
- Always sync the latest pipeline run before building:
  ```bash
  uv run python scripts/sync_generated_bundle.py --run {run_id} --doc aeon-trespass-core
  ```

## Screenshot Pages
- Default pages captured: 1, 3, 10, 35, 50, 70
- These are chosen to cover: cover page, table of contents, early content, mid-content, late content
- URL pattern: `http://localhost:3002/docs/aeon-trespass-core/page`

## Build Failures
- If `pnpm --filter reader build` fails with type errors, run `make schemas` first — contracts may be out of date.
- If it fails with missing generated data, the bundle hasn't been synced.

## Assertion Failures
- "No text content" on a page usually means the bundle is missing or corrupt for that page.
- "Console errors" are often hydration mismatches — check if the bundle schema matches the reader's TypeScript types.
