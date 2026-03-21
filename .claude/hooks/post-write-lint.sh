#!/usr/bin/env bash
# Claude Code PostToolUse hook: runs fast lint on written/edited files
# Informational only — warns but never blocks
set -uo pipefail

# Extract file_path from tool input JSON
FILE_PATH=$(echo "$CLAUDE_TOOL_INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//;s/"$//')

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# Resolve to repo root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

case "$FILE_PATH" in
  *.py)
    # Fast single-file ruff check
    OUTPUT=$(cd "$REPO_ROOT" && uv run ruff check "$FILE_PATH" 2>&1) || true
    if [ -n "$OUTPUT" ]; then
      echo "⚠️  ruff check found issues in $FILE_PATH:"
      echo "$OUTPUT"
    fi
    ;;
  *.ts|*.tsx)
    # Fast single-file eslint
    if [ -f "$REPO_ROOT/apps/reader/node_modules/.bin/eslint" ]; then
      OUTPUT=$(cd "$REPO_ROOT/apps/reader" && npx eslint "$REPO_ROOT/$FILE_PATH" --no-warn-ignored --max-warnings=999 2>&1) || true
      if echo "$OUTPUT" | grep -qE '(error|warning)'; then
        echo "⚠️  eslint found issues in $FILE_PATH:"
        echo "$OUTPUT"
      fi
    fi
    ;;
esac

# Always exit 0 — this hook is informational only
exit 0
