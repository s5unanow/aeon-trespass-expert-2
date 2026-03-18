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

1. `ruff check` — no lint errors (includes McCabe complexity C901, max 12)
2. `ruff format --check` — no format violations
3. `mypy --strict` — no type errors (72+ source files)
4. `pytest` — all tests pass
5. `tsc` — frontend type check (contracts + reader)
6. `import-linter` — no import cycle violations (models↛stages, llm↛stages, etc.)

CI runs gates 1-6 on every push. Pre-commit hook enforces 1-5 automatically; run `uv run lint-imports` manually for gate 6.

## Development workflow (MANDATORY)

All work is tracked in **Linear** (project **ATE2**, team **S5U**). Every change follows this workflow — no exceptions.

### 1. Pick up an issue
- If the user specifies an issue, use that one
- **If no issue is specified, auto-pick**: query Linear for the highest-priority unassigned issue in the earliest milestone: `mcp__linear__list_issues(project="ATE2", state="Backlog")` — pick the first Urgent, then High, then Normal
- Update issue status to **In Progress**: `mcp__linear__save_issue(id="S5U-XXX", state="In Progress")`

### 2. Create a branch
- Branch from `main`: `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description`
- Branch naming is **enforced by hook** — must match `s5unanow/s5u-<number>-<description>`
- Direct commits to `main` are **blocked by hook**
- Dirty working tree on main is **blocked by hook** — stash or discard before branching

### 3. Work on the branch
- Commit early and often with prefix `S5U-XXX: description`
- Quality gates (ruff, mypy, eslint, tsc, pytest) run automatically before each commit via hook

### 4. Definition of done (all must be true before PR)
- [ ] Code changes directly address the Linear issue description
- [ ] New/changed code has tests (unless pure config/docs change)
- [ ] No new `except Exception` without structured logging
- [ ] Import boundaries respected (`uv run lint-imports`)
- [ ] Full checks pass: `make lint && make typecheck && make test`

### 5. Sub-agent code review (MANDATORY before PR)
- **You MUST spawn a review agent before creating a PR.** This is not optional.
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- If the review agent says **BLOCK**, fix the issues before proceeding
- If only warnings/nits, use judgement — fix warnings, nits are optional

### 6. Create PR
- Push branch: `git push -u origin HEAD`
- Create PR via `gh pr create` with summary and test plan
- Link the Linear issue in PR body

### 7. Wait for CI
- Check CI status: `gh pr checks <pr-number> --watch`
- If CI fails, fix and push — do not merge with red CI

### 8. Merge and sync
- Merge via: `gh pr merge <pr-number> --squash --delete-branch`
- Sync local: `git checkout main && git pull`
- Update Linear issue to **Done**: `mcp__linear__save_issue(id="S5U-XXX", state="Done")`

### Rollback process
If a merged PR breaks something:
1. Identify the merge commit: `git log --oneline main`
2. Revert it: `git revert <commit-sha>` (creates a new commit, does NOT rewrite history)
3. Push the revert, open a new PR for the fix
4. Reopen the Linear issue and set back to **In Progress**
- **Never** use `git reset --hard` or `git push --force` on main

## Conventions

- **Commit prefixes**: `S5U-XXX:` referencing the Linear issue
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

All work is tracked in Linear (project ATE2). Check `mcp__linear__list_issues(project="ATE2")` for current status.

Core pipeline (stages 00–08) and reader are functional. Remaining work covers reliability, testing, and polish — see Linear milestones for priorities.

## Pipeline stages (15-stage order)

```
00_resolve → 01_ingest → 02_extract → 03_normalize → 04_resolve_assets →
05_plan_translation → 06_translate → 07_merge → 08_enrich → 09_evaluate_qa →
10_fix → 11_export → 12_build → 13_index → 14_release
```

Stage implementations go in `packages/pipeline/src/aeon_reader_pipeline/stages/`.
