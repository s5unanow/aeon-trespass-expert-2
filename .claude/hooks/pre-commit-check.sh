#!/usr/bin/env bash
# Claude Code PreToolUse hook: enforces branch discipline + quality gates before git commit
# Receives CLAUDE_TOOL_INPUT as JSON with the Bash command
set -euo pipefail

# Only intercept git commit commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git commit'; then
  exit 0
fi

cd "$(git rev-parse --show-toplevel)"

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

# ── Detect staged file types ──
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR)

if [ -z "$STAGED_FILES" ]; then
  echo "✅ No staged files — skipping quality gates."
  exit 0
fi

HAS_PYTHON=false
HAS_FRONTEND=false

if echo "$STAGED_FILES" | grep -qE '\.py$'; then
  HAS_PYTHON=true
fi

if echo "$STAGED_FILES" | grep -qE '\.(ts|tsx|js|jsx|css|scss)$'; then
  HAS_FRONTEND=true
fi

if [ "$HAS_PYTHON" = false ] && [ "$HAS_FRONTEND" = false ]; then
  echo "✅ No Python or frontend files staged — skipping quality gates."
  exit 0
fi

echo "🔍 Running pre-commit quality gates (python=$HAS_PYTHON, frontend=$HAS_FRONTEND)..."

GATE=0
TOTAL=0
if [ "$HAS_PYTHON" = true ]; then TOTAL=$((TOTAL + 4)); fi   # ruff check, ruff format, mypy, pytest
if [ "$HAS_FRONTEND" = true ]; then TOTAL=$((TOTAL + 2)); fi # pnpm lint, tsc

MAX_FAIL_LINES=30
GATE_OUTPUT=$(mktemp)
trap 'rm -f "$GATE_OUTPUT"' EXIT

# ── run_gate: capture output, show summary on pass, truncated output on fail ──
# Usage: run_gate "label" "fail_message" command [args...]
run_gate() {
  local label="$1" fail_msg="$2"
  shift 2

  GATE=$((GATE + 1))
  echo "  [$GATE/$TOTAL] $label..."

  if "$@" > "$GATE_OUTPUT" 2>&1; then
    echo "  ✓ $label passed"
  else
    local total_lines
    total_lines=$(wc -l < "$GATE_OUTPUT")
    if [ "$total_lines" -gt "$MAX_FAIL_LINES" ]; then
      head -n "$MAX_FAIL_LINES" "$GATE_OUTPUT"
      echo "  ... ($((total_lines - MAX_FAIL_LINES)) more lines truncated)"
    else
      cat "$GATE_OUTPUT"
    fi
    echo ""
    echo "❌ BLOCKED: $fail_msg"
    exit 1
  fi
}

# ── Python gates ──
if [ "$HAS_PYTHON" = true ]; then
  run_gate "ruff check" \
    "ruff check failed. Fix lint errors before committing." \
    uv run ruff check packages/pipeline/src/ tests/

  run_gate "ruff format --check" \
    "ruff format failed. Run 'ruff format' to fix." \
    uv run ruff format --check packages/pipeline/src/ tests/

  run_gate "mypy --strict" \
    "mypy failed. Fix type errors before committing." \
    uv run mypy --strict packages/pipeline/src/
fi

# ── Frontend gates ──
if [ "$HAS_FRONTEND" = true ]; then
  run_gate "pnpm lint" \
    "ESLint failed. Fix frontend lint errors before committing." \
    bash -c 'cd apps/reader && pnpm lint'

  run_gate "tsc --noEmit" \
    "tsc failed. Fix TypeScript errors before committing." \
    bash -c 'cd apps/reader && pnpm tsc --noEmit'
fi

# ── Python tests ──
if [ "$HAS_PYTHON" = true ]; then
  run_gate "pytest (fast)" \
    "Tests failed. Fix failing tests before committing." \
    uv run pytest tests/ -x -q --timeout=60 -m "not slow"
fi

echo "✅ All quality gates passed."
exit 0
