# Architecture 3 — Agent Execution Rules

Standing discipline reference for agents implementing Architecture 3 tickets.

Companion documents:
- [ARCH3_EXECUTION_PLAYBOOK.md](ARCH3_EXECUTION_PLAYBOOK.md) — implementation sequencing and verification
- [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md) — hard-page fixtures and phase exit checklist

---

## 1. Ticket discipline

**One ticket at a time.** Work exactly one leaf issue per branch. Do not batch multiple issues into one PR.

**Never implement umbrella issues.** S5U-245, S5U-246, S5U-247, S5U-248, S5U-249, S5U-250 are coordination-only. If your assigned ticket is an epic or umbrella, stop and pick a leaf issue under it instead.

**Check prerequisites before starting.** Consult the [execution playbook](ARCH3_EXECUTION_PLAYBOOK.md) for the ticket's prerequisites. If a prerequisite is not Done, do not start the ticket — pick a different ready ticket or escalate.

**Stay in scope.** Implement what the ticket describes. Do not add features, refactor adjacent code, or "improve" things outside the ticket's acceptance criteria. If you discover something that needs fixing, file a comment on the relevant issue or create a new issue — do not fix it in this branch.

---

## 2. Branch and commit discipline

- Branch from `main`: `git checkout main && git pull && git checkout -b s5unanow/s5u-XXX-short-description`
- Commit prefix: `S5U-XXX: description`
- One PR per ticket. Squash merge when done.
- Run quality gates before every commit: `make lint && make typecheck && make test`
- Run `uv run lint-imports` before pushing to verify import boundary compliance.

---

## 3. Contract and schema rules

When touching Pydantic models (`packages/pipeline/src/**/models/`):

1. **Regenerate schemas immediately:** run `make schemas` after any model change.
2. **Verify downstream types compile:** `make typecheck` must pass (includes `tsc` for generated TS types).
3. **Update tests:** if a model field is added/removed/renamed, update all tests that construct or assert on that model.
4. **Never edit generated files by hand.** Files in `packages/contracts/` are generated from Pydantic models. Edit the Python model, then regenerate.
5. **Contract direction is one-way:** Python Pydantic → JSON Schema → TypeScript. Never create TypeScript types manually for pipeline contracts.

---

## 4. Fixture rules

Fixtures live in `tests/fixtures/pdf/` and are cataloged in [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md).

**When you can update fixtures in your ticket:**
- The ticket explicitly says to add or curate a fixture (e.g., evaluation tickets like S5U-277, S5U-290)
- The ticket explicitly names a fixture that needs creation

**When you cannot update fixtures:**
- You are implementing a stage or contract change and your tests would be easier with different fixture expectations
- You want to change what a fixture "should" produce to match your implementation

If your implementation changes what a fixture produces and the new output is correct, that expectation change goes in a **separate evaluation ticket or a separate commit** with explicit justification — never silently in the same diff as the behavior change.

**Never introduce ad hoc test PDFs** outside the catalog. If you need a new fixture, add it to the catalog first (or escalate if you don't have an evaluation ticket for it).

---

## 5. Legacy path rules

The existing pipeline path (`extract_primitives → normalize_layout → resolve_assets_symbols → ...`) must remain runnable throughout the Architecture 3 migration.

**Do not delete legacy stages or functions** until S5U-265 exit criteria pass (side-by-side comparison proves the new path is equivalent or better).

**Do not break legacy imports.** If you move or rename a module that legacy stages depend on, update the legacy import sites or add a compatibility re-export. Prefer updating imports over adding shims — but never leave legacy stages broken.

**New Architecture 3 code is additive.** New stages, contracts, and modules should exist alongside the legacy path. They are invoked via explicit mode, flag, or stage range — not by replacing legacy entry points.

**Verify legacy still works** as part of every PR: run the pipeline on `simple_text.pdf` through the legacy path and confirm it produces a valid bundle. This is a blocking phase exit criterion at every phase.

---

## 6. Migration safety

**Do not remove heuristics prematurely.** Existing heuristics in `normalize_layout` and `resolve_assets_symbols` may be wrong, but they are load-bearing until the Architecture 3 replacement is verified. Mark them with comments like `# LEGACY: replaced by S5U-XXX once verified` rather than deleting them.

**Feature flags or explicit modes for new paths.** If your ticket introduces a new processing path that could affect output, gate it behind an explicit mechanism (CLI flag, config option, or stage name) so it can be toggled independently.

**No silent behavioral changes.** If your change alters pipeline output for any existing fixture or document, that change must be visible in the PR (golden diff, test output change, or explicit acknowledgment in the PR description).

---

## 7. Escalation rules

**Stop and escalate** (comment on the Linear issue, set status to Blocked) when:

- The ticket's acceptance criteria are ambiguous — you are guessing what "done" means
- A prerequisite ticket is listed as Done but the expected artifact or API does not exist
- You need to break a legacy stage to implement the new path
- A fixture does not exist and the ticket assumes it does
- A contract change cascades into more than 3 downstream files unexpectedly
- You encounter `make test` failures in unrelated code that you cannot resolve
- The ticket requires adding a new external dependency not in the current `pyproject.toml`

**Escalation means:** add a comment on the Linear issue explaining the specific blocker, move the issue back to **Backlog**, and pick a different ready ticket. Do not improvise a workaround that violates these rules. (The team workflow statuses are: Backlog, Todo, In Progress, In Review, Done, Canceled, Duplicate — there is no "Blocked" status.)

---

## 8. Review and PR rules

Before creating a PR:

1. Run all quality gates: `make lint && make typecheck && make test && uv run lint-imports`
2. Spawn the review sub-agent (`.claude/prompts/review.md`) — this is mandatory per CLAUDE.md
3. If the review says **BLOCK**, fix the issues before proceeding
4. Link the Linear issue in the PR body

After CI passes:

- Squash merge via `gh pr merge <number> --squash --delete-branch`
- Sync local: `git checkout main && git pull`
- Update Linear issue to Done

---

## 9. Quick checklist (per ticket)

```
[ ] Ticket is a leaf issue, not an umbrella/epic
[ ] Prerequisites are Done (check playbook)
[ ] Branch created from latest main
[ ] Changes are in scope — nothing extra
[ ] Contract changes → make schemas → make typecheck
[ ] Fixture changes → only if ticket explicitly allows
[ ] Legacy path still works (simple_text.pdf end-to-end)
[ ] make lint && make typecheck && make test → all green
[ ] uv run lint-imports → passes
[ ] Review sub-agent → no BLOCK
[ ] PR created with Linear link
[ ] CI green → squash merge → update Linear
```
