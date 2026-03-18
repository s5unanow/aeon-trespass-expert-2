#!/usr/bin/env bash
# Claude Code PreToolUse hook: enforces branch discipline + quality gates before git commit
# Receives CLAUDE_TOOL_INPUT as JSON with the Bash command
set -euo pipefail

# Only intercept git commit commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git commit'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-2

# ── Guard 1: Never commit on main ──
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  echo "❌ BLOCKED: Direct commits to '$BRANCH' are not allowed."
  echo "Create a feature branch first: git checkout -b s5unanow/s5u-XXX-description"
  exit 1
fi

# ── Guard 2: Branch must follow Linear naming convention ──
if ! echo "$BRANCH" | grep -qiE '^s5unanow/s5u-[0-9]+-'; then
  echo "❌ BLOCKED: Branch '$BRANCH' does not follow naming convention."
  echo "Expected: s5unanow/s5u-<issue-number>-<description>"
  echo "Example:  s5unanow/s5u-117-add-retry-backoff"
  exit 1
fi

# Skip quality gates for amend (minor fixups, gates already passed on original commit)
if echo "$CLAUDE_TOOL_INPUT" | grep -q -- '--amend'; then
  echo "✅ Branch guards passed (skipping quality gates for amend)."
  exit 0
fi

echo "🔍 Running pre-commit quality gates..."

# Gate 1: ruff check
echo "  [1/5] ruff check..."
if ! uv run ruff check packages/pipeline/src/ tests/ 2>&1; then
  echo ""
  echo "❌ BLOCKED: ruff check failed. Fix lint errors before committing."
  exit 1
fi

# Gate 2: ruff format
echo "  [2/5] ruff format --check..."
if ! uv run ruff format --check packages/pipeline/src/ tests/ 2>&1; then
  echo ""
  echo "❌ BLOCKED: ruff format failed. Run 'ruff format' to fix."
  exit 1
fi

# Gate 3: pnpm lint (ESLint for reader)
echo "  [3/5] pnpm lint..."
if ! (cd apps/reader && pnpm lint 2>&1); then
  echo ""
  echo "❌ BLOCKED: ESLint failed. Fix frontend lint errors before committing."
  exit 1
fi

# Gate 4: typecheck (mypy + tsc)
echo "  [4/5] typecheck..."
if ! uv run mypy --strict packages/pipeline/src/ 2>&1; then
  echo ""
  echo "❌ BLOCKED: mypy failed. Fix type errors before committing."
  exit 1
fi

if ! (cd apps/reader && pnpm tsc --noEmit 2>&1); then
  echo ""
  echo "❌ BLOCKED: tsc failed. Fix TypeScript errors before committing."
  exit 1
fi

# Gate 5: pytest (fail-fast, skip slow integration tests)
echo "  [5/5] pytest (fast)..."
if ! uv run pytest tests/ -x -q --timeout=60 -m "not slow" 2>&1; then
  echo ""
  echo "❌ BLOCKED: Tests failed. Fix failing tests before committing."
  exit 1
fi

echo "✅ All quality gates passed."
exit 0
