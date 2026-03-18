#!/usr/bin/env node
/**
 * Generate TypeScript types from Pydantic models.
 *
 * This is a convenience wrapper — the actual generation is done by
 * the Python script `scripts/gen_contracts.py` which produces both
 * JSON Schema and TypeScript in a single pass.
 *
 * Usage: node scripts/generate-types.mjs
 *    or: make schemas  (recommended)
 */

import { execSync } from "child_process";

try {
  execSync("uv run python scripts/gen_contracts.py", {
    cwd: new URL("../../..", import.meta.url).pathname,
    stdio: "inherit",
  });
} catch {
  process.exit(1);
}
