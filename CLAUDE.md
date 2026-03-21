# CLAUDE.md — Aeon Trespass Expert

Content compiler + static reader for Aeon Trespass rulebook translation (EN→RU).
Monorepo: **packages/pipeline** (Python 3.12) and **apps/reader** (Next.js 15).

## Quality gates (must pass before commit)

1. `ruff check` — no lint errors (McCabe C901, max 12)
2. `ruff format --check` — no format violations
3. `mypy --strict` — no type errors
4. `pytest` — all tests pass
5. `tsc` — frontend type check
6. `import-linter` — no import cycle violations (`uv run lint-imports`)

Pre-commit hook enforces 1-5 automatically (scoped by file type). Run gate 6 manually.

## Development workflow (MANDATORY)

All work tracked in **Linear** (project **ATE2**, team **S5U**). No exceptions.

### 1. Pick up an issue
- Use the specified issue, or **auto-pick** highest-priority unassigned from earliest milestone
- Set to **In Progress**: `mcp__linear__save_issue(id="S5U-XXX", state="In Progress")`

### 2. Create a branch
- `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description`
- Naming enforced by hook: `s5unanow/s5u-<number>-<description>`
- Direct commits to `main` are **blocked by hook**

### 3. Work on the branch
- Commit early and often with prefix `S5U-XXX: description`
- Quality gates run automatically before each commit via hook

### 4. Definition of done
- [ ] Issue has explicit acceptance criteria (if missing, add them before starting)
- [ ] Code changes directly address the Linear issue
- [ ] New/changed code has tests (unless pure config/docs)
- [ ] No `except Exception` without structured logging
- [ ] Import boundaries respected (`uv run lint-imports`)
- [ ] `make lint && make typecheck && make test` passes

### 5. Sub-agent code review (MANDATORY before PR)
- **You MUST spawn a review agent before creating a PR.** This is not optional.
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- **BLOCK** → fix before proceeding; warnings → fix; nits → optional

### 6. Create PR → CI → Merge
- `git push -u origin HEAD` → `gh pr create` (link Linear issue)
- `gh pr checks <number> --watch` — do not merge with red CI
- `gh pr merge <number> --squash --delete-branch` → sync local → set Linear to **Done**

### Rollback
- `git revert <sha>` — never `reset --hard` or `push --force` on main

## Conventions

- **Commit prefixes**: `S5U-XXX:` referencing the Linear issue
- **Path-scoped rules**: `.claude/rules/pipeline.md`, `reader.md`, `contracts.md` — loaded automatically by file path

## Reference (read on demand)

- `docs/PROJECT_ARCHITECTURE.md` — full system design
- `docs/PROJECT_ARCHITECTURE_TO_AGENTIC.md` — locked implementation decisions
- `docs/PIPELINE_STAGES.md` — 16-stage pipeline order (canonical registry: `stage_framework/registry.py`)
- `Makefile` — all available commands (`make bootstrap`, `make lint`, etc.)
