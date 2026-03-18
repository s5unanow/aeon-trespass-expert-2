---
name: verify-reader
description: Build the reader site, serve it, screenshot key pages, and run assertions to verify it works
user_invocable: true
---

# Verify Reader

Verify the Next.js reader works after pipeline or frontend changes. This skill builds the site, serves it, captures screenshots, and runs programmatic checks.

## Quick Verification

```bash
# 1. Build static site
pnpm --filter reader build

# 2. Serve and screenshot (in one step)
.claude/skills/verify-reader/scripts/verify.sh
```

## Full Manual Workflow

### Step 1: Ensure bundle is synced
If you just ran the pipeline, sync first:
```bash
uv run python scripts/sync_generated_bundle.py \
    --run {run_id} --doc aeon-trespass-core \
    --target apps/reader/generated
```

### Step 2: Build static site
```bash
pnpm --filter reader build
```
Output goes to `apps/reader/out/`.

### Step 3: Serve locally
```bash
npx serve apps/reader/out -l 3002 &
SERVER_PID=$!
```

### Step 4: Capture screenshots
```bash
node scripts/screenshot.mjs
# Or specific pages:
node scripts/screenshot.mjs 1 3 10 35
```
Screenshots saved to `artifacts/screenshots/page-NN.png`.

### Step 5: Run assertions
```bash
node .claude/skills/verify-reader/scripts/assert-pages.mjs
```

### Step 6: Cleanup
```bash
kill $SERVER_PID
```

## What Gets Checked

The assertion script verifies:
1. **Pages load** — HTTP 200 for key page URLs
2. **No console errors** — No JS errors in browser console
3. **Content present** — Page body has non-trivial text content
4. **Sidebar renders** — Navigation sidebar element exists
5. **Images load** — No broken image tags (if images exist on page)

## When to Run This

- After any change to `apps/reader/` components or styles
- After pipeline changes that affect the site bundle format
- After syncing a new pipeline run to the reader
- Before creating a PR that touches reader or pipeline export code

## Read gotchas.md for common issues.
