---
name: health
description: Audit Claude Code configuration — hooks, rules, skills, memory, and toolchain
user_invocable: true
---

# Health Check

Audit the Claude Code configuration for this project. Read and validate each config file, then output a structured report.

## Checks to perform

Run all checks below. For each, report PASS, WARN, or FAIL.

### 1. CLAUDE.md
- Read `CLAUDE.md` — verify it exists
- Count lines — WARN if over 80 lines
- Verify it contains "Development workflow" and "Quality gates" sections

### 2. Settings
- Read `.claude/settings.json` — verify valid JSON
- Verify `PreToolUse` hooks array exists with at least one entry
- Verify `PostToolUse` hooks array exists with at least one entry
- Verify each hook `command` path points to an existing file

### 3. Hook scripts
- List all `.claude/hooks/*.sh` files
- For each: verify file exists and is executable (`ls -la`)
- Verify `pre-commit-check.sh` exists (critical gate)

### 4. Rules files
- List `.claude/rules/*.md` files
- For each: read the file and verify it has `globs:` in the YAML frontmatter
- Verify at least `pipeline.md`, `reader.md`, `contracts.md` exist

### 5. Skills
- List `.claude/skills/*/skill.md` files
- For each: verify it has valid frontmatter with `name`, `description`, `user_invocable`
- Verify critical skills exist: `autopilot`, `babysit-prs`, `run-pipeline`, `verify-reader`, `health`

### 6. Review prompt
- Verify `.claude/prompts/review.md` exists and is non-empty

### 7. Memory
- Read memory `MEMORY.md` index file
- For each linked memory file: verify it exists on disk
- WARN on any orphaned memory files (on disk but not in index)
- WARN on any broken links (in index but not on disk)

### 8. Quality gate tools
Run these version checks (FAIL if any tool is missing):
```bash
uv run ruff --version
uv run mypy --version
pnpm --version
```

## Output format

Print results grouped by priority:

```
## FIX NOW (blocking issues)
- [FAIL] description...

## STRUCTURAL ISSUES (should fix soon)
- [WARN] description...

## ALL GOOD
- [PASS] description...
```

If everything passes, print: "All health checks passed — configuration is consistent."
