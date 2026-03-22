#!/usr/bin/env bash
# test-run-issues.sh — Verify orphan cleanup behaviour in run-issues.sh.
#
# Tests:
#   1. EXIT trap fires orphan cleanup on "no more issues" exit path
#   2. EXIT trap fires on normal loop completion (max-issues)
#   3. Cleanup prompt targets team S5U (not project ATE2)
#
# Runs entirely with stubbed `claude` and `gh` — no network calls.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_DIR=$(mktemp -d)
CLEANUP_LOG="$TEST_DIR/cleanup_calls.log"

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------
# Create a bin dir with fake `claude` and `gh` that appear first in PATH.
STUB_BIN="$TEST_DIR/bin"
mkdir -p "$STUB_BIN"

# Fake `claude` — first call simulates autopilot outputting "no more issues",
# subsequent calls (orphan cleanup) just log the prompt.
cat > "$STUB_BIN/claude" <<'STUBEOF'
#!/usr/bin/env bash
prompt="${*}"
# Detect orphan cleanup invocations (the -p flag value contains "In Progress")
if echo "$prompt" | grep -q "In Progress"; then
  echo "$prompt" >> "${CLEANUP_LOG}"
  echo "No orphaned issues found."
  exit 0
fi
# Simulate autopilot: output "no more actionable issues"
echo "Checked backlog — no more actionable issues in the backlog."
exit 0
STUBEOF
chmod +x "$STUB_BIN/claude"

cat > "$STUB_BIN/gh" <<'STUBEOF'
#!/usr/bin/env bash
echo ""
exit 0
STUBEOF
chmod +x "$STUB_BIN/gh"

export PATH="$STUB_BIN:$PATH"
export CLEANUP_LOG
export COOLDOWN=0
export MAX_TURNS=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
pass=0
fail=0

assert() {
  local desc="$1"
  shift
  if "$@"; then
    echo "  PASS: $desc"
    pass=$((pass + 1))
  else
    echo "  FAIL: $desc"
    fail=$((fail + 1))
  fi
}

# ---------------------------------------------------------------------------
# Test 1: "no more issues" exit path still triggers EXIT trap cleanup
# ---------------------------------------------------------------------------
echo "Test 1: EXIT trap fires on 'no more issues' exit"
> "$CLEANUP_LOG"  # reset

bash "$SCRIPT_DIR/run-issues.sh" --max-issues 5 > "$TEST_DIR/test1_output.log" 2>&1 || true

assert "cleanup was called at least once" \
  test -s "$CLEANUP_LOG"

assert "cleanup prompt targets team S5U (not project ATE2)" \
  grep -q "team S5U" "$CLEANUP_LOG"

assert "cleanup prompt does NOT mention project ATE2" \
  bash -c '! grep -q "project ATE2" "'"$CLEANUP_LOG"'"'

# ---------------------------------------------------------------------------
# Test 2: max-issues exit also triggers cleanup via trap
# ---------------------------------------------------------------------------
echo "Test 2: EXIT trap fires on max-issues exit"

# Make claude stub succeed (simulate a verified run) so max-issues is reached
cat > "$STUB_BIN/claude" <<'STUBEOF'
#!/usr/bin/env bash
prompt="${*}"
if echo "$prompt" | grep -q "In Progress"; then
  echo "$prompt" >> "${CLEANUP_LOG}"
  echo "No orphaned issues found."
  exit 0
fi
# Simulate successful autopilot run (no "no more issues" phrase)
echo "Picked up S5U-999. Implemented. PR merged."
exit 0
STUBEOF
chmod +x "$STUB_BIN/claude"

# Also fake a "growing" autopilot log so verification passes
FAKE_LOG_DIR="$TEST_DIR/autopilot_data"
mkdir -p "$FAKE_LOG_DIR"
FAKE_LOG="$FAKE_LOG_DIR/autopilot.log"

# Patch: create a stub claude that also appends to the fake log
cat > "$STUB_BIN/claude" <<STUBEOF
#!/usr/bin/env bash
prompt="\${*}"
if echo "\$prompt" | grep -q "In Progress"; then
  echo "\$prompt" >> "${CLEANUP_LOG}"
  echo "No orphaned issues found."
  exit 0
fi
# Append to autopilot log so post-run verification succeeds
echo "run" >> "${FAKE_LOG}"
echo "Picked up S5U-999. Implemented. PR merged."
exit 0
STUBEOF
chmod +x "$STUB_BIN/claude"

> "$CLEANUP_LOG"  # reset

# Override AUTOPILOT_LOG location by wrapping the script
AUTOPILOT_LOG="$FAKE_LOG" bash -c '
  export AUTOPILOT_LOG
  source /dev/stdin
' < <(
  # Re-export into the script env
  sed "s|AUTOPILOT_LOG=.*|AUTOPILOT_LOG=\"$FAKE_LOG\"|" "$SCRIPT_DIR/run-issues.sh"
) -- --max-issues 1 > "$TEST_DIR/test2_output.log" 2>&1 || true

assert "cleanup was called on max-issues exit" \
  test -s "$CLEANUP_LOG"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $pass passed, $fail failed"
rm -rf "$TEST_DIR"

if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
