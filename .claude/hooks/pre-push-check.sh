#!/usr/bin/env bash
# Claude Code PreToolUse hook: block direct pushes to main
set -euo pipefail

# Only intercept git push commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git push'; then
  exit 0
fi

cd "$(git rev-parse --show-toplevel)"

BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  # Emergency escape hatch: ALLOW_MAIN_PUSH=1 git push ...
  if [ "${ALLOW_MAIN_PUSH:-0}" = "1" ]; then
    echo "⚠️  ALLOW_MAIN_PUSH=1 — bypassing main push protection."
    exit 0
  fi

  if echo "$CLAUDE_TOOL_INPUT" | grep -qE 'force|--force|-f'; then
    echo "❌ BLOCKED: Force push to '$BRANCH' is not allowed."
    exit 1
  fi

  echo "❌ BLOCKED: Direct pushes to '$BRANCH' are blocked. Use a PR instead."
  exit 1
fi

echo "✅ Push guard passed."
exit 0
