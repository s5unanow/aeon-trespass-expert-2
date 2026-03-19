# Development and Release Loop

This guide covers the supported workflow for developing, testing, and releasing changes to the Aeon Trespass Expert pipeline and reader.

## Prerequisites

```bash
make bootstrap   # Python (uv) + Node (pnpm)
```

## Branch workflow

All work is tracked in Linear (project ATE2, team S5U).

1. **Pick an issue** from Linear backlog
2. **Create a branch**: `git checkout -b s5unanow/s5u-XXX-short-description`
   - Branch naming is enforced by hook: `s5unanow/s5u-<number>-<description>`
   - Direct commits to `main` are blocked
3. **Commit early and often** with prefix `S5U-XXX: description`
4. **Quality gates run automatically** via pre-commit hook (ruff, mypy, tsc, pytest)

## Quality gates

Run all checks locally before pushing:

```bash
make lint          # ruff check + ruff format --check + eslint
make typecheck     # mypy --strict + tsc
make test          # pytest + vitest
uv run lint-imports  # import boundary checks
```

## Pipeline development

### Running the pipeline

```bash
# Mock run (no API key, fast iteration)
reader-pipeline run --doc aeon-trespass-core --mock

# Dry run with cost estimate
reader-pipeline run --doc aeon-trespass-core --dry-run

# Full run with Gemini
reader-pipeline run --doc aeon-trespass-core

# Run specific stage range
reader-pipeline run --doc aeon-trespass-core --from extract_primitives --to normalize_layout

# Force re-run (ignore cache)
reader-pipeline run --doc aeon-trespass-core --cache-mode force_refresh
```

### Inspecting runs

```bash
reader-pipeline inspect <run-id> --doc aeon-trespass-core
```

Artifacts are written to `artifacts/runs/<run-id>/<doc-id>/`.

### Contract changes

When modifying Pydantic models that affect the reader:

```bash
make schemas       # Regenerate JSON Schema + TypeScript
make check-generated  # Verify generated files match
```

Direction: Python Pydantic → JSON Schema → TypeScript (never edit TS types manually).

## Reader development

```bash
make site-dev      # Start Next.js dev server
make site-build    # Static export to apps/reader/out/
make e2e           # Run Playwright E2E tests (requires built site)
```

The reader consumes bundle data from `apps/reader/generated/`. To update it after a pipeline run, sync from the export stage output.

## PR and merge flow

1. Run all gates: `make lint && make typecheck && make test`
2. Push: `git push -u origin HEAD`
3. Create PR: `gh pr create` with summary and test plan
4. Wait for CI: `gh pr checks <number> --watch`
5. Merge: `gh pr merge <number> --squash --delete-branch`
6. Sync: `git checkout main && git pull`
7. Update Linear issue to Done

## CI pipeline

CI runs on every PR and push to main:

- **backend**: ruff, mypy, bandit, pytest with coverage
- **contracts**: verifies generated schemas match source
- **frontend**: eslint, tsc, vitest, Next.js build
- **e2e**: Playwright smoke tests against fixture bundle

## Rollback

If a merged PR breaks something:

```bash
git log --oneline main        # Find the merge commit
git revert <commit-sha>       # Create revert commit
git push                      # Push revert, open fix PR
```

Never use `git reset --hard` or `git push --force` on main.
