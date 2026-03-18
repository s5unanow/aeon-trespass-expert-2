#!/usr/bin/env bash
# Claude Code PreToolUse hook: block direct pushes to main
set -euo pipefail

# Only intercept git push commands
if ! echo "$CLAUDE_TOOL_INPUT" | grep -q 'git push'; then
  exit 0
fi

cd /Users/s5una/projects/aeon-trespass-expert-2

BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
  # Allow if it's just syncing (git push with no special args after a merge)
  # Block if it looks like pushing direct work to main
  if echo "$CLAUDE_TOOL_INPUT" | grep -qE 'force|--force|-f'; then
    echo "❌ BLOCKED: Force push to '$BRANCH' is not allowed."
    exit 1
  fi
fi

echo "✅ Push guard passed."
exit 0
