#!/usr/bin/env bash
# run-issues.sh — Hands-off autopilot runner for Linear issues.
#
# Runs Claude Code's /autopilot skill in a loop, one issue per invocation.
# The /autopilot skill handles issue selection (highest-priority unassigned
# from earliest milestone), implementation, review, PR, CI, and merge.
#
# Usage:
#   ./scripts/run-issues.sh                    # run until no issues remain
#   ./scripts/run-issues.sh --max-issues 3     # process at most 3 issues
#   MAX_TURNS=120 ./scripts/run-issues.sh      # override turn budget
#
# Recommended: run inside tmux for long sessions:
#   tmux new -s issues
#   ./scripts/run-issues.sh
#   # Ctrl+B, D to detach
#   # tmux attach -t issues to check back
#
# Environment variables:
#   MAX_TURNS  — Claude max turns per issue (default: 80)
#   COOLDOWN   — Seconds to wait between issues (default: 5)

set -uo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MAX_TURNS="${MAX_TURNS:-80}"
COOLDOWN="${COOLDOWN:-5}"
MAX_ISSUES=0  # 0 = unlimited
AUTOPILOT_LOG=".claude/skills/autopilot/data/autopilot.log"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 [--max-issues N]"
  echo ""
  echo "Options:"
  echo "  --max-issues N   Stop after processing N issues (default: unlimited)"
  echo ""
  echo "Environment variables:"
  echo "  MAX_TURNS   Max turns per issue (default: 80)"
  echo "  COOLDOWN    Seconds between issues (default: 5)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-issues)
      if [[ -z "${2:-}" ]] || ! [[ "${2:-}" =~ ^[0-9]+$ ]]; then
        echo "Error: --max-issues requires a positive integer"
        exit 1
      fi
      MAX_ISSUES="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
issue_count=0
success_count=0
failure_count=0
consecutive_failures=0
MAX_CONSECUTIVE_FAILURES=3

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# Count lines in autopilot log (0 if file doesn't exist)
log_line_count() {
  if [[ -f "$AUTOPILOT_LOG" ]]; then
    wc -l < "$AUTOPILOT_LOG" | tr -d ' '
  else
    echo 0
  fi
}

# Get the most recent merged PR number (empty if none)
latest_merged_pr() {
  gh pr list --state merged --limit 1 --json number --jq '.[0].number // empty' 2>/dev/null || echo ""
}

# Reset orphaned In Progress issues via a lightweight Claude call
reset_orphaned_issues() {
  log "Checking for orphaned In Progress issues..."
  local cleanup_prompt
  cleanup_prompt="List all issues in Linear project ATE2 with state 'In Progress'. "
  cleanup_prompt+="For each, check if a git branch exists (git branch -a | grep s5u-<number>) "
  cleanup_prompt+="and if an open PR exists (gh pr list --search 'S5U-<number>'). "
  cleanup_prompt+="If an issue has NO matching branch AND no open PR, reset it to Backlog "
  cleanup_prompt+="via mcp__linear__save_issue(id=..., state='Backlog'). "
  cleanup_prompt+="Report what you found. Be concise."

  claude -p "$cleanup_prompt" \
    --dangerously-skip-permissions \
    --max-turns 10 \
    2>&1 | while IFS= read -r line; do log "  [orphan-check] $line"; done
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
limit_label="unlimited"
if [[ "$MAX_ISSUES" -gt 0 ]]; then
  limit_label="$MAX_ISSUES"
fi
log "Autopilot runner started (MAX_TURNS=$MAX_TURNS, MAX_ISSUES=$limit_label, COOLDOWN=${COOLDOWN}s)"

while true; do
  # Check max-issues limit
  if [[ "$MAX_ISSUES" -gt 0 && "$issue_count" -ge "$MAX_ISSUES" ]]; then
    log "Reached max-issues limit ($MAX_ISSUES). Stopping."
    break
  fi

  issue_count=$((issue_count + 1))
  log "--- Starting issue run #$issue_count ---"

  # Capture pre-run state for merge verification
  pre_log_lines=$(log_line_count)
  pre_merged_pr=$(latest_merged_pr)

  output_file=$(mktemp)

  # Run /autopilot for one issue. Capture output for stop-condition detection.
  # Each claude -p invocation is non-interactive: the autopilot skill picks one
  # issue, implements it, merges the PR, and exits.
  claude -p "/autopilot" \
    --dangerously-skip-permissions \
    --max-turns "$MAX_TURNS" \
    2>&1 | tee "$output_file"
  exit_code=${PIPESTATUS[0]}

  # Detect when autopilot reports no remaining issues
  if grep -qiE "no.*(backlog|actionable|remaining).*issues|no more.*issues|no issues" "$output_file" 2>/dev/null; then
    log "No more actionable issues found. Stopping."
    rm -f "$output_file"
    break
  fi

  # --- Post-run verification ---
  # Exit code 0 only means Claude didn't crash. Verify actual work was done.
  run_verified=false

  # Check 1: Did the autopilot log grow by at least one entry?
  post_log_lines=$(log_line_count)
  if [[ "$post_log_lines" -gt "$pre_log_lines" ]]; then
    log "Verified: autopilot log grew ($pre_log_lines -> $post_log_lines lines)"
    run_verified=true
  fi

  # Check 2: Was a new PR merged since the run started?
  if [[ "$run_verified" != true ]]; then
    post_merged_pr=$(latest_merged_pr)
    if [[ -n "$post_merged_pr" && "$post_merged_pr" != "$pre_merged_pr" ]]; then
      log "Verified: new merged PR detected (#$post_merged_pr)"
      run_verified=true
    fi
  fi

  if [[ "$run_verified" == true ]]; then
    log "Issue run #$issue_count completed and verified"
    success_count=$((success_count + 1))
    consecutive_failures=0
  else
    log "Issue run #$issue_count NOT verified (exit code: $exit_code, no merged PR or log entry)"
    failure_count=$((failure_count + 1))
    consecutive_failures=$((consecutive_failures + 1))

    # Reset any orphaned In Progress issues
    reset_orphaned_issues

    if [[ "$consecutive_failures" -ge "$MAX_CONSECUTIVE_FAILURES" ]]; then
      log "Hit $MAX_CONSECUTIVE_FAILURES consecutive failures. Stopping to avoid infinite loop."
      rm -f "$output_file"
      break
    fi
  fi

  rm -f "$output_file"

  # Cooldown to avoid rate limits
  log "Cooling down for ${COOLDOWN}s before next issue..."
  sleep "$COOLDOWN"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log "=== Autopilot runner finished ==="
log "Runs: $issue_count | Succeeded: $success_count | Failed: $failure_count"
