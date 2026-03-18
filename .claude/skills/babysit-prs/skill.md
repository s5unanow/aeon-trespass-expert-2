---
name: babysit-prs
description: Monitor a PR's CI status, fix failures, merge when green, and update Linear
user_invocable: true
---

# Babysit PRs

Monitor a pull request through CI, fix any failures, merge when green, and close the Linear issue.

## Usage

When invoked, check if there's an open PR on the current branch. If not, ask the user which PR to babysit.

## The Babysit Loop

### Step 1: Identify the PR
```bash
# Get current branch's PR
gh pr view --json number,title,state,headRefName
# Or list open PRs
gh pr list --state open
```

### Step 2: Watch CI
```bash
gh pr checks <pr-number> --watch
```

If `--watch` hangs for more than 10 minutes, fall back to polling:
```bash
gh pr checks <pr-number>
```

### Step 3: Handle CI Result

**If CI passes:**
```bash
# Squash merge and delete branch
gh pr merge <pr-number> --squash --delete-branch

# Sync local
git checkout main && git pull
```

Then update Linear:
```
mcp__linear__save_issue(id="S5U-XXX", state="Done")
```

**If CI fails:**
1. Identify the failing job:
   ```bash
   gh pr checks <pr-number>
   ```
2. Get failure logs:
   ```bash
   gh run view <run-id> --log-failed
   ```
3. Diagnose and fix the issue on the branch
4. Commit with the issue prefix: `S5U-XXX: fix CI failure`
5. Push: `git push`
6. Go back to Step 2

### Step 4: Report

After merging, report:
- PR number and title
- Number of CI attempts
- Final status
- Linear issue updated to Done

Log the result to `.claude/skills/babysit-prs/data/babysit.log`.

## Failure Limits

- **Max 3 CI fix attempts.** If CI fails 3 times on different issues, stop and ask the user. Something deeper is wrong.
- **Same failure twice** = likely not a flaky test. Investigate root cause, don't just retry.
- **Pre-existing failures** = check if the failure exists on `main` too (`git stash && git checkout main && make test`). If it does, it's not your fault — note it and proceed.

## Log Format

Append to `.claude/skills/babysit-prs/data/babysit.log`:
```
[2026-03-18T16:30:00Z] PR #42 (S5U-181) — MERGED after 1 CI attempt
[2026-03-18T17:15:00Z] PR #43 (S5U-182) — MERGED after 2 CI attempts (fixed: ruff format)
[2026-03-18T18:00:00Z] PR #44 (S5U-183) — STOPPED after 3 CI attempts (user intervention needed)
```

## Important Rules

- **Never force-push to main.**
- **Always squash merge** — keeps main history clean.
- **Don't skip hooks** — if pre-commit fails, fix the issue properly.
- **Check the failure is yours** — compare against main before assuming your code broke it.
