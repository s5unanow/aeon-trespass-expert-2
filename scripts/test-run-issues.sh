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

cleanup_test_dir() {
  if [[ "${fail:-0}" -eq 0 ]]; then
    rm -rf "$TEST_DIR"
  else
    echo "  (test artifacts preserved at $TEST_DIR for debugging)"
  fi
}
trap cleanup_test_dir EXIT

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------
# Create a bin dir with fake `claude` and `gh` that appear first in PATH.
STUB_BIN="$TEST_DIR/bin"
mkdir -p "$STUB_BIN"

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

# Stub claude: autopilot outputs "no more issues", cleanup calls log the prompt
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

# Fake autopilot log so post-run verification succeeds
FAKE_LOG="$TEST_DIR/autopilot.log"
export AUTOPILOT_LOG="$FAKE_LOG"

# Stub claude: successful autopilot run + append to fake log for verification
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

bash "$SCRIPT_DIR/run-issues.sh" --max-issues 1 > "$TEST_DIR/test2_output.log" 2>&1 || true

assert "cleanup was called on max-issues exit" \
  test -s "$CLEANUP_LOG"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $pass passed, $fail failed"

if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
