#!/usr/bin/env bash
# Full reader verification: build → serve → screenshot → assert → cleanup.
# Usage: .claude/skills/verify-reader/scripts/verify.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PORT=3002

cd "$PROJECT_ROOT"

echo "=== Reader Verification ==="

# Step 1: Build
echo ""
echo "[1/4] Building static site..."
pnpm --filter reader build
echo "Build complete."

# Step 2: Serve
echo ""
echo "[2/4] Starting local server on port $PORT..."
npx serve apps/reader/out -l "$PORT" &>/dev/null &
SERVER_PID=$!

# Ensure cleanup on exit (register immediately after capturing PID)
cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Give server time to start
sleep 2

# Check server is up
if ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" | grep -q "200"; then
  echo "ERROR: Server failed to start on port $PORT"
  exit 1
fi
echo "Server running (PID $SERVER_PID)."

# Step 3: Screenshots
echo ""
echo "[3/4] Capturing screenshots..."
mkdir -p artifacts/screenshots
node scripts/screenshot.mjs 2>/dev/null || echo "WARNING: Screenshot capture had errors (Playwright may not be installed)"

# Step 4: Assertions
echo ""
echo "[4/4] Running assertions..."
node "$SCRIPT_DIR/assert-pages.mjs"

echo ""
echo "=== Verification Complete ==="
echo "Screenshots saved to artifacts/screenshots/"
