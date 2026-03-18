---
name: autopilot
description: Autonomous work loop — pick a Linear issue, implement, test, review, PR, merge, repeat
user_invocable: true
---

# Autopilot

Continuous autonomous work loop. Picks up Linear issues, implements them, and merges PRs with minimal human intervention.

## The Loop

Each iteration:

### 1. Pick Issue
Query Linear for the highest-priority unassigned Backlog issue in the earliest incomplete milestone:
```
mcp__linear__list_issues(project="ATE2", state="Backlog")
```
Priority order: Urgent > High > Normal > Low. Within same priority, pick from the earliest milestone.

If no Backlog issues remain, report to the user and stop.

### 2. Set In Progress
```
mcp__linear__save_issue(id="S5U-XXX", state="In Progress")
```

### 3. Create Branch
```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-XXX-short-description
```

### 4. Implement
- Read the issue description carefully
- Explore relevant code before making changes
- Commit early and often with prefix `S5U-XXX: description`
- Write tests for new/changed code (unless pure config/docs)

### 5. Quality Gates
```bash
make lint && make typecheck && make test
```
Also run import linter: `uv run lint-imports`

### 6. Verify (conditional)
**If pipeline code changed** (`packages/pipeline/`):
- Use the `run-pipeline` skill knowledge to verify pipeline still works
- At minimum, run `uv run reader-pipeline run --doc aeon-trespass-core --mock` to check stages execute

**If reader code changed** (`apps/reader/`):
- Build the reader: `pnpm --filter reader build`
- If Playwright is available, run the verify-reader assertions

**If export format changed**:
- Run both pipeline mock and reader build

### 7. Code Review
**MANDATORY.** Spawn a sub-agent with the review prompt:
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- If verdict is **BLOCK**, fix all critical issues before proceeding
- If only warnings, fix them. Nits are optional.

### 8. Create PR
```bash
git push -u origin HEAD
```
Create PR via `gh pr create` with:
- Title: short, descriptive
- Body: summary, Linear issue link (`Closes S5U-XXX`), test plan
- Follow the PR template in `.github/pull_request_template.md`

### 9. Babysit
Follow the `babysit-prs` skill:
- Watch CI with `gh pr checks <number> --watch`
- Fix failures (max 3 attempts)
- Squash merge when green
- Sync local main
- Update Linear to Done

### 10. Next Issue
**Always ask the user before starting the next issue.** Report:
- What was completed (issue ID, PR number)
- What the next highest-priority issue would be
- Ask for confirmation to proceed

## Config

Defaults are in `.claude/skills/autopilot/data/config.json`. Edit to customize:
```json
{
  "ask_before_next_issue": true,
  "max_ci_failures_before_stop": 3,
  "run_pipeline_verification": "auto"
}
```

- `ask_before_next_issue`: Always true. Pause between issues to let the user review.
- `max_ci_failures_before_stop`: Stop babysitting after this many CI failures.
- `run_pipeline_verification`: `"auto"` = only if pipeline code changed. `"always"` = every time. `"never"` = skip.

## Run Log

Append each completed issue to `.claude/skills/autopilot/data/autopilot.log`:
```
[2026-03-18T16:30:00Z] S5U-138 — DONE (PR #42, 1 CI attempt)
[2026-03-18T17:45:00Z] S5U-139 — DONE (PR #43, 2 CI attempts)
[2026-03-18T18:30:00Z] S5U-140 — BLOCKED (review found critical issues, user intervention needed)
```

## Safety Rails

- **Never loop infinitely.** Always pause between issues.
- **3-strike rule.** If any step fails 3 times, stop and report to the user.
- **Pipeline costs money.** Only run real translation (`translate_units`) if explicitly needed. Default to `--mock`.
- **Don't skip review.** The sub-agent review is mandatory per CLAUDE.md.
- **CLAUDE.md is the source of truth.** This skill codifies the workflow but doesn't override project rules.
- **Respect merge freezes.** If there's a known freeze, stop and report.
