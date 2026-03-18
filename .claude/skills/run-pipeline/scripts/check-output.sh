#!/usr/bin/env bash
# Quick sanity check on pipeline stage output.
# Usage: .claude/skills/run-pipeline/scripts/check-output.sh <run_id> <doc_id> [artifact_root]
set -euo pipefail

RUN_ID="${1:?Usage: check-output.sh <run_id> <doc_id> [artifact_root]}"
DOC_ID="${2:?Usage: check-output.sh <run_id> <doc_id> [artifact_root]}"
ROOT="${3:-artifacts}"

RUN_DIR="$ROOT/runs/$RUN_ID/$DOC_ID"

if [ ! -d "$RUN_DIR" ]; then
  echo "ERROR: Run directory not found: $RUN_DIR"
  exit 1
fi

echo "=== Pipeline Output Check ==="
echo "Run:  $RUN_ID"
echo "Doc:  $DOC_ID"
echo "Root: $ROOT"
echo ""

# Check each stage directory
for stage_dir in "$RUN_DIR"/*/; do
  stage_name=$(basename "$stage_dir")
  file_count=$(find "$stage_dir" -type f | wc -l | tr -d ' ')
  json_count=$(find "$stage_dir" -name '*.json' -type f | wc -l | tr -d ' ')

  # Check if stage manifest exists
  manifest="$stage_dir/stage_manifest.json"
  if [ -f "$manifest" ]; then
    status=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" "$manifest" 2>/dev/null || echo "unknown")
  else
    status="no manifest"
  fi

  printf "  %-25s %3d files (%d json)  [%s]\n" "$stage_name" "$file_count" "$json_count" "$status"
done

# Check site bundle specifically
BUNDLE_DIR="$RUN_DIR/11_export/site_bundle/$DOC_ID"
echo ""
if [ -d "$BUNDLE_DIR" ]; then
  bundle_files=$(find "$BUNDLE_DIR" -type f | wc -l | tr -d ' ')
  echo "Site bundle: $bundle_files files"

  # Validate JSON files in bundle
  invalid=0
  while IFS= read -r -d '' f; do
    if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
      echo "  INVALID JSON: $f"
      invalid=$((invalid + 1))
    fi
  done < <(find "$BUNDLE_DIR" -name '*.json' -print0)

  if [ "$invalid" -eq 0 ]; then
    echo "All bundle JSON files are valid."
  else
    echo "WARNING: $invalid invalid JSON files in bundle."
  fi
else
  echo "Site bundle: NOT FOUND (stage 11 may not have run)"
fi

echo ""
echo "=== Check Complete ==="
