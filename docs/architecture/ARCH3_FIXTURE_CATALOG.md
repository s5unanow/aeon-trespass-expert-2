# Architecture 3 — Fixture Catalog & Phase Exit Checklist

Canonical fixture set and phase exit criteria for all Architecture 3 evaluation work.

Companion documents:
- [ARCH3_EXECUTION_PLAYBOOK.md](ARCH3_EXECUTION_PLAYBOOK.md) — implementation sequencing and verification
- [ARCH3_AGENT_RULES.md](ARCH3_AGENT_RULES.md) — agent execution discipline

Parent issue: `S5U-245`

---

## 1. Fixture catalog

All fixtures live under `tests/fixtures/pdf/`. Agents must use these fixtures — do not introduce ad hoc test PDFs without an explicit evaluation ticket.

### 1.1 Existing fixtures

| Fixture ID | File | Category | Purpose |
|-----------|------|----------|---------|
| `simple_text` | `simple_text.pdf` | Simple | Basic text extraction, paragraph/heading classification |
| `multiformat` | `multiformat.pdf` | Simple | Mixed content types (headings, lists, tables, images) |
| `with_images` | `with_images.pdf` | Simple | Image extraction, figure/caption linkage basics |

### 1.2 Required hard-page fixtures (to be added)

These fixtures must be curated from the Aeon Trespass source material before Phase 2 implementation begins. Each represents a specific layout challenge.

| Fixture ID | Category | Layout challenge | Expected route | Consuming issues |
|-----------|----------|-----------------|----------------|-----------------|
| `two_column` | Hard | Standard 2-column body text | `semantic` | S5U-255, S5U-256, S5U-290 |
| `column_with_sidebar` | Hard | 2-column body + sidebar/aside panel | `semantic` | S5U-255, S5U-256, S5U-262 |
| `full_width_interrupt` | Hard | Column flow interrupted by full-width heading/figure | `semantic` | S5U-255, S5U-256 |
| `dense_figures` | Hard | Multiple figures with captions on one page | `semantic` | S5U-260, S5U-277, S5U-290 |
| `inline_symbols` | Hard | Body text with inline game icons (raster + vector) | `semantic` | S5U-257, S5U-258, S5U-277 |
| `table_in_callout` | Hard | Table nested inside a bordered callout box | `semantic` | S5U-261, S5U-262 |
| `vector_icons` | Hard | Vector-drawn symbols (not embedded rasters) | `semantic` | S5U-257, S5U-258, S5U-259 |
| `decorative_heavy` | Hard | Page with borders, ornaments, background art | `semantic` | S5U-254, S5U-258 |
| `mixed_hard` | Hard | Columns + callouts + figures + inline symbols combined | `hybrid` | S5U-263, S5U-265, S5U-279, S5U-280 |
| `layout_extreme` | Hard | Dense multi-column with nested containers and vector art | `facsimile` | S5U-263, S5U-265, S5U-280 |

### 1.3 Quality concerns by fixture

Each fixture maps to one or more quality concerns that Architecture 3 must address:

| Quality concern | Description | Fixtures that test it |
|----------------|-------------|----------------------|
| **Reading order** | Multi-column linearization, sidebar handling, full-width interruptions | `two_column`, `column_with_sidebar`, `full_width_interrupt` |
| **Symbol detection** | Inline/prefix/cell-local symbol identification and classification | `inline_symbols`, `vector_icons`, `decorative_heavy` |
| **Figure/caption** | Figure region grouping, caption linkage, orphan detection | `dense_figures`, `with_images` |
| **Table extraction** | Region-scoped table detection, false positive avoidance | `table_in_callout`, `multiformat` |
| **Callout/container** | Bordered/shaded container detection and internal structure | `column_with_sidebar`, `table_in_callout` |
| **Furniture separation** | Header/footer/border/ornament filtering | `decorative_heavy` |
| **Fallback routing** | Confidence-driven semantic/hybrid/facsimile routing | `mixed_hard`, `layout_extreme` |
| **End-to-end** | Full pipeline through bundle, reader build, search | `mixed_hard`, `layout_extreme`, `simple_text` |

---

## 2. Phase exit checklist

A phase is complete when all its hard gates are green. Diagnostic checks are informational — they should be reviewed but do not block the next phase.

### Phase 1: Evidence Contracts

| # | Check | Type | Verification |
|---|-------|------|-------------|
| 1 | `CanonicalPageEvidence`, `PrimitivePageEvidence`, `ResolvedPageIR` models exist and validate | **Blocking** | `make schemas && make typecheck` |
| 2 | Provenance IDs and normalized coordinates are present in extraction artifacts | **Blocking** | Schema validation tests (S5U-276) pass |
| 3 | Stage DAG has explicit evidence → region → semantic boundary | **Blocking** | `make test` — stage ordering tests pass |
| 4 | Legacy path (`extract_primitives → normalize_layout → ...`) still runs end-to-end | **Blocking** | Pipeline run on `simple_text.pdf` produces valid bundle |
| 5 | New contracts round-trip through JSON serialization | **Blocking** | Schema validation tests (S5U-276) pass |
| 6 | Import boundaries hold for new modules | **Blocking** | `uv run lint-imports` passes |

### Phase 2: Page Topology

| # | Check | Type | Verification |
|---|-------|------|-------------|
| 1 | Furniture/template detection emits `TemplateAssignment` for fixture pages | **Blocking** | Pipeline run on `decorative_heavy` produces artifact |
| 2 | `PageRegionGraph` emitted for all hard-page fixtures | **Blocking** | All hard fixtures produce region graphs |
| 3 | Multi-column pages have correct column assignment in `PageReadingOrder` | **Blocking** | `two_column` and `column_with_sidebar` pass reading-order assertions |
| 4 | Full-width interruptions handled correctly | **Blocking** | `full_width_interrupt` pass reading-order assertions |
| 5 | Legacy path still runs end-to-end | **Blocking** | Pipeline run on `simple_text.pdf` produces valid bundle |
| 6 | Region graphs are inspectable (overlay or dump) | Diagnostic | Manual review of region overlay output |

### Phase 3: Visual Assets & Entities

| # | Check | Type | Verification |
|---|-------|------|-------------|
| 1 | Asset registry contains all embedded rasters and vector clusters for fixture pages | **Blocking** | S5U-257 tests pass on `inline_symbols`, `vector_icons` |
| 2 | Symbol candidates generated from text, raster, and vector evidence | **Blocking** | S5U-277 evaluation harness passes on `inline_symbols`, `vector_icons` |
| 3 | Symbol anchor types (inline, line_prefix, cell_local, block) are correct | **Blocking** | S5U-277 checks anchor type distribution |
| 4 | Decorative elements filtered from semantic symbols | **Blocking** | `decorative_heavy` — no furniture/ornaments classified as semantic symbols |
| 5 | Figure-caption linkage correct on `dense_figures` | **Blocking** | No orphan captions, no unlinked figures |
| 6 | Table extraction scoped to regions — no false positives from callout borders | **Blocking** | `table_in_callout` — table found inside callout, callout border not a table |
| 7 | Callout containers detected and structured | **Blocking** | `table_in_callout`, `column_with_sidebar` — callout blocks emitted with children |
| 8 | Legacy path still runs end-to-end | **Blocking** | Pipeline run on `simple_text.pdf` produces valid bundle |

### Phase 4: Hard-Page Rollout

| # | Check | Type | Verification |
|---|-------|------|-------------|
| 1 | Page confidence scores emitted for all fixture pages | **Blocking** | S5U-263 confidence contracts validate |
| 2 | `mixed_hard` routes to `hybrid`, `layout_extreme` routes to `facsimile` | **Blocking** | S5U-280 fallback-routing tests pass |
| 3 | Simple pages still route to `semantic` | **Blocking** | `simple_text`, `multiformat` route correctly |
| 4 | Extraction/entity QA rules fire on Architecture 3 fixtures | **Blocking** | S5U-278 QA tests pass |
| 5 | Hard-page goldens exist and match within tolerance | **Blocking** | S5U-265 golden comparison passes |
| 6 | Architecture 3 path runs beside legacy with comparable or better output | **Blocking** | S5U-265 side-by-side comparison |
| 7 | End-to-end test: PDF → bundle → reader build → search index | **Blocking** | S5U-279 e2e test passes on `mixed_hard` |
| 8 | Intermediate topology/entity goldens stable | **Blocking** | S5U-290 golden harness passes |
| 9 | Overlays/review artifacts inspectable for all hard-page fixtures | Diagnostic | Manual review of overlays |
| 10 | Legacy heuristics identified for deletion or compatibility marking | Diagnostic | Audit log in S5U-265 PR |

---

## 3. Fixture management rules

1. **No ad hoc fixtures.** Every fixture PDF must be registered in this catalog with an ID, category, and purpose.

2. **Fixture expectations are stable.** Expected outputs (golden files, route classifications, assertion counts) must not change in the same PR that changes the code producing those outputs. Expectation changes go in evaluation tickets.

3. **Hard-page fixtures require source material.** Fixtures tagged "Hard" must come from real Aeon Trespass pages, not synthetic PDFs. They should be curated to represent the specific layout challenge named in the catalog.

4. **Adding a new fixture** requires:
   - An evaluation ticket or explicit scope in an existing ticket
   - Entry in this catalog with fixture ID, category, purpose, and consuming issues
   - At minimum one consuming test that asserts something about the fixture

5. **Fixture location:** all fixture PDFs go in `tests/fixtures/pdf/`. Named by fixture ID with `.pdf` extension.

---

## 4. How to use this catalog

- **Before implementing a leaf issue:** check which fixtures your issue consumes (column "Consuming issues" in section 1.2). Ensure those fixtures exist. If they don't, that is a blocker — escalate per the [execution playbook](ARCH3_EXECUTION_PLAYBOOK.md).

- **Before claiming a phase is done:** run through the phase exit checklist. Every **Blocking** check must be green. Document the results in the phase epic's Linear issue.

- **When adding evaluation tests:** reference fixture IDs from this catalog, not arbitrary file paths. This keeps test code consistent and traceable.
