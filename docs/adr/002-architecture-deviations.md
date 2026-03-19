# ADR-002: Known Architecture Deviations

**Status:** Accepted
**Date:** 2026-03-19

## Context

An architecture audit compared the documented system design (`docs/PROJECT_ARCHITECTURE.md`) against the actual codebase. Several deviations were found where the implementation does not yet match the architecture's claims.

This ADR records the known deviations and their planned resolution, rather than allowing them to remain implicit.

## Deviations

### 1. Manifest-only build/search/release stages

**Claimed:** Stages 12 (build_reader), 13 (index_search), and 14 (package_release) produce real build/search/release artifacts.

**Actual:** These stages record manifests but do not execute real build operations. `build_reader` does not invoke Next.js. `index_search` does not run Pagefind. `package_release` writes metadata but does not assemble a deployable artifact.

**Resolution:** S5U-220 — either implement real stage operations or demote to documented operator scripts.

### 2. Single-document operator path

**Claimed:** The pipeline supports multi-document translation with a catalog.

**Actual:** `configs/catalog.yaml` lists only one document. The second document config (`aeon-trespass-odyssey.yaml`) references a nonexistent source PDF. The reader builds its catalog by scanning directories rather than consuming a single authoritative catalog artifact.

**Resolution:** S5U-222 — prove multi-doc with a real second document or fixture.

### 3. Placeholder stages and modules

**Claimed:** All 15 stages in the canonical pipeline perform meaningful work.

**Actual:** `apply_safe_fixes` is a pass-through. `qa/rules/layout_rules.py` and `qa/rules/search_rules.py` are empty placeholders. `config/patch_loader.py` and `config/symbol_loader.py` are scaffolding.

**Resolution:** Resolved in S5U-225. The `apply_safe_fixes` pass-through stage was removed from the canonical DAG — `export_site_bundle` now reads directly from `enrich_content`. The four empty placeholder modules (`layout_rules`, `search_rules`, `patch_loader`, `symbol_loader`) were deleted. The pipeline is now 14 stages.

### 4. Hybrid/facsimile fallback

**Claimed:** Layout-heavy pages fall back to hybrid or facsimile rendering.

**Actual:** `render_mode` is carried as a flag but no explicit fallback asset contract exists. The reader assumes semantic blocks are always present.

**Resolution:** S5U-221 — implement first-class fallback in contracts and reader.

## Consequences

- These deviations are now tracked explicitly instead of being implied by stale documentation.
- Each deviation has a Linear issue assigned for resolution.
- Future audits should compare against this ADR to verify deviations have been closed.
- New deviations discovered during implementation should be added here or in new ADRs.
