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

### 2. Verify Acceptance Criteria
The issue **must** have an explicit "Acceptance Criteria" or "Definition of done" section before implementation begins.
- If the issue lacks acceptance criteria, **stop and ask the user** to add them
- Alternatively, draft acceptance criteria based on the issue description and present them for user approval before proceeding
- Do not guess what "done" looks like — it must be written down
- If acceptance criteria cannot be confirmed, **abandon the issue** (see Cleanup on Failure below) — do not claim it

### 3. Set In Progress
Only after confirming acceptance criteria exist and the issue is workable:
```
mcp__linear__save_issue(id="S5U-XXX", state="In Progress")
```

### 4. Create Branch
```bash
git checkout main && git pull
git checkout -b s5unanow/s5u-XXX-short-description
```

### 5. Implement
- Read the issue description and acceptance criteria carefully
- Explore relevant code before making changes
- Commit early and often with prefix `S5U-XXX: description`
- Write tests for new/changed code (unless pure config/docs)

### 6. Quality Gates
```bash
make lint && make typecheck && make test
```
Also run import linter: `uv run lint-imports`

### 7. Verify (conditional)
**If pipeline code changed** (`packages/pipeline/`):
- Use the `run-pipeline` skill knowledge to verify pipeline still works
- At minimum, run `uv run reader-pipeline run --doc aeon-trespass-core --mock` to check stages execute

**If reader code changed** (`apps/reader/`):
- Build the reader: `pnpm --filter reader build`
- If Playwright is available, run the verify-reader assertions

**If export format changed**:
- Run both pipeline mock and reader build

### 8. Code Review
**MANDATORY.** Spawn a sub-agent with the review prompt:
- Read `.claude/prompts/review.md` and use it as the Agent prompt
- If verdict is **BLOCK**, fix all critical issues before proceeding
- If only warnings, fix them. Nits are optional.

### 9. Create PR
```bash
git push -u origin HEAD
```
Create PR via `gh pr create` with:
- Title: short, descriptive
- Body: summary, Linear issue link (`Closes S5U-XXX`), test plan
- Follow the PR template in `.github/pull_request_template.md`

### 10. Babysit
Follow the `babysit-prs` skill:
- Watch CI with `gh pr checks <number> --watch`
- Fix failures (max 3 attempts)
- Squash merge when green
- Sync local main
- Update Linear to Done

### 11. Next Issue
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

Append each completed or abandoned issue to `.claude/skills/autopilot/data/autopilot.log`:
```
[2026-03-18T16:30:00Z] S5U-138 — DONE (PR #42, 1 CI attempt)
[2026-03-18T17:45:00Z] S5U-139 — DONE (PR #43, 2 CI attempts)
[2026-03-18T18:30:00Z] S5U-140 — BLOCKED (review found critical issues, user intervention needed)
[2026-03-18T19:00:00Z] S5U-141 — SKIPPED (missing prerequisites: depends on S5U-135)
[2026-03-18T19:05:00Z] S5U-142 — ABANDONED (max turns approaching, incomplete implementation)
```

## Cleanup on Failure

If at any point the current issue cannot be completed — blocking error, missing prerequisites, max turns approaching, or any unrecoverable situation — you **must** clean up before exiting:

1. **Reset the issue to Backlog** (only if it was set to In Progress):
   ```
   mcp__linear__save_issue(id="S5U-XXX", state="Backlog")
   ```

2. **Log the outcome** to `.claude/skills/autopilot/data/autopilot.log` with status `SKIPPED` or `ABANDONED`:
   - `SKIPPED` — issue could not be started (missing prerequisites, no acceptance criteria, depends on another issue)
   - `ABANDONED` — work started but could not be finished (max turns, blocking error, review BLOCK that can't be resolved)
   - Always include the reason in parentheses

3. **Clean up any partial branch** if no commits were made:
   ```bash
   git checkout main
   git branch -D s5unanow/s5u-XXX-short-description  # only if no commits pushed
   ```

4. **Report to the user** what happened and why the issue was abandoned

This cleanup is **mandatory**. Never exit a session leaving an issue in "In Progress" with no branch, commits, or PR.

## Safety Rails

- **One issue at a time.** Never work multiple issues or PRs in parallel. The current issue must be merged or abandoned before picking up the next (see CLAUDE.md).
- **Never loop infinitely.** Always pause between issues.
- **3-strike rule.** If any step fails 3 times, stop and report to the user.
- **Pipeline costs money.** Only run real translation (`translate_units`) if explicitly needed. Default to `--mock`.
- **Don't skip review.** The sub-agent review is mandatory per CLAUDE.md.
- **CLAUDE.md is the source of truth.** This skill codifies the workflow but doesn't override project rules.
- **Respect merge freezes.** If there's a known freeze, stop and report.
