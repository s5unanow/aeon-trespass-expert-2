# Hard-Page Fixture Catalog

Canonical fixture set for pipeline regression testing.

All fixtures live under `tests/fixtures/pdf/`. Do not introduce ad hoc test PDFs without an explicit evaluation ticket.

---

## 1. Fixture catalog

### 1.1 Existing fixtures

| Fixture ID | File | Category | Purpose |
|-----------|------|----------|---------|
| `simple_text` | `simple_text.pdf` | Simple | Basic text extraction, paragraph/heading classification |
| `multiformat` | `multiformat.pdf` | Simple | Mixed content types (headings, lists, tables, images) |
| `with_images` | `with_images.pdf` | Simple | Image extraction, figure/caption linkage basics |

### 1.2 Hard-page fixtures

| Fixture ID | Category | Layout challenge | Expected route |
|-----------|----------|-----------------|----------------|
| `two_column` | Hard | Standard 2-column body text | `semantic` |
| `column_with_sidebar` | Hard | 2-column body + sidebar/aside panel | `semantic` |
| `full_width_interrupt` | Hard | Column flow interrupted by full-width heading/figure | `semantic` |
| `dense_figures` | Hard | Multiple figures with captions on one page | `semantic` |
| `inline_symbols` | Hard | Body text with inline game icons (raster + vector) | `semantic` |
| `table_in_callout` | Hard | Table nested inside a bordered callout box | `semantic` |
| `vector_icons` | Hard | Vector-drawn symbols (not embedded rasters) | `semantic` |
| `decorative_heavy` | Hard | Page with borders, ornaments, background art | `semantic` |
| `mixed_hard` | Hard | Columns + callouts + figures + inline symbols combined | `hybrid` |
| `layout_extreme` | Hard | Dense multi-column with nested containers and vector art | `facsimile` |

### 1.3 Quality concerns by fixture

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

## 2. Fixture management rules

1. **No ad hoc fixtures.** Every fixture PDF must be registered in this catalog with an ID, category, and purpose.

2. **Fixture expectations are stable.** Expected outputs (golden files, route classifications, assertion counts) must not change in the same PR that changes the code producing those outputs. Expectation changes go in separate evaluation tickets.

3. **Hard-page fixtures require source material.** Fixtures tagged "Hard" must come from real Aeon Trespass pages, not synthetic PDFs. They should be curated to represent the specific layout challenge named in the catalog.

4. **Adding a new fixture** requires:
   - An evaluation ticket or explicit scope in an existing ticket
   - Entry in this catalog with fixture ID, category, and purpose
   - At minimum one consuming test that asserts something about the fixture

5. **Fixture location:** all fixture PDFs go in `tests/fixtures/pdf/`. Named by fixture ID with `.pdf` extension.
