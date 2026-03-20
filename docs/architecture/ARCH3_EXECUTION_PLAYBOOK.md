# Architecture 3 — Execution Playbook

Canonical sequencing, verification, and migration reference for all Architecture 3 work.

Companion documents:
- [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md) — hard-page fixtures and phase exit checklist
- [ARCH3_AGENT_RULES.md](ARCH3_AGENT_RULES.md) — agent execution discipline

Parent issue: `S5U-245`

---

## 1. Backlog structure

### Umbrella vs leaf issues

| Type | Issues | Rule |
|------|--------|------|
| **Root umbrella** | S5U-245 | Never implement directly. Tracks overall migration. |
| **Phase epics** | S5U-246, S5U-247, S5U-248, S5U-249, S5U-250 | Never implement directly. Coordinate leaf work within a phase. |
| **Planning/process** | S5U-295, S5U-296, S5U-297 | Produce documentation artifacts. No pipeline code changes. |
| **Leaf issues** | All others under the epics | Implementation-ready. One branch, one PR per leaf. |

**Rule:** Only leaf issues produce code changes. Epics and umbrellas are closed when all their children are done.

---

## 2. Canonical implementation sequence

### Phase 1: Evidence Contracts

Goal: introduce evidence-layer contracts and split the stage DAG so semantic classification happens after evidence resolution.

| Order | Issue | Title | Prerequisites | Type |
|-------|-------|-------|---------------|------|
| 1.1 | S5U-251 | Define `CanonicalPageEvidence`, `PrimitivePageEvidence`, `ResolvedPageIR` contracts | None | Contract |
| 1.2 | S5U-253 | Introduce normalized coordinates, provenance IDs, raster-provider handles | S5U-251 | Contract + extraction |
| 1.3 | S5U-252 | Refactor the stage DAG for evidence → region → semantic flow | S5U-251, S5U-253 | Stage refactor |
| 1.4 | S5U-276 | Add schema-validation test suite for persisted Architecture 3 artifacts | S5U-251 | Test |

**Phase 1 exit criteria:** see [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md).

### Phase 2: Page Topology

Goal: deterministic region segmentation and reading-order reconstruction.

| Order | Issue | Title | Prerequisites | Type |
|-------|-------|-------|---------------|------|
| 2.1 | S5U-254 | Implement document-level furniture and page-template detection | Phase 1 complete | Stage implementation |
| 2.2 | S5U-255 | Emit `PageRegionGraph` with bands, containers, sidebars | S5U-254 | Stage implementation |
| 2.3 | S5U-256 | Implement `PageReadingOrder` for multi-column flow | S5U-255 | Stage implementation |

**Phase 2 exit criteria:** see [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md).

### Phase 3: Visual Assets & Entities

Goal: document-wide asset catalog, symbol resolution, and entity linking.

Two parallel tracks once Phase 2 is complete:

**Track A — Asset catalog and symbols (S5U-248)**

| Order | Issue | Title | Prerequisites | Type |
|-------|-------|-------|---------------|------|
| 3A.1 | S5U-257 | Build cross-page asset registry | Phase 2 complete | Stage implementation |
| 3A.2 | S5U-258 | Generate symbol candidates from text, raster, vector evidence | S5U-257 | Stage implementation |
| 3A.3 | S5U-259 | Extend IR and bundle contracts with symbol anchor types | S5U-258 | Contract + export |
| 3A.4 | S5U-277 | Add symbol evaluation harness | S5U-258 | Test |

**Track B — Figures, tables, callouts (S5U-249)**

| Order | Issue | Title | Prerequisites | Type |
|-------|-------|-------|---------------|------|
| 3B.1 | S5U-260 | Link figures and captions from local region/asset graphs | Phase 2 complete, S5U-257 | Stage implementation |
| 3B.2 | S5U-261 | Scope table extraction to candidate regions | S5U-255 (regions) | Stage implementation |
| 3B.3 | S5U-262 | Promote callout/container detection | S5U-255 (regions) | Stage implementation |

Tracks A and B can run in parallel after S5U-257 lands. S5U-260 depends on the asset registry (S5U-257) for figure region grouping.

**Phase 3 exit criteria:** see [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md).

### Phase 4: Hard-Page Rollout

Goal: confidence-driven fallback, evaluation harnesses, goldens, and side-by-side migration.

| Order | Issue | Title | Prerequisites | Type |
|-------|-------|-------|---------------|------|
| 4.1 | S5U-263 | Add page/block confidence contracts and fallback-routing policy | Phase 3 complete | Contract + routing |
| 4.2 | S5U-278 | Implement extraction/entity QA rules, make blocking on fixtures | S5U-263 | QA rules |
| 4.3 | S5U-264 | Create evidence/order/assets/entities overlays for debugging | S5U-263 | Review tooling |
| 4.4 | S5U-265 | Create hard-page goldens and run Architecture 3 beside legacy | S5U-263, S5U-278 | Golden + migration |
| 4.5 | S5U-280 | Add fallback-routing consistency tests | S5U-263 | Test |
| 4.6 | S5U-290 | Add intermediate topology/entity golden harness | S5U-265 | Test |
| 4.7 | S5U-279 | Add end-to-end hard-page fixture test (PDF → bundle → reader → search) | S5U-265 | Test |

**Phase 4 exit criteria:** see [ARCH3_FIXTURE_CATALOG.md](ARCH3_FIXTURE_CATALOG.md).

---

## 3. Verification expectations by ticket type

Every leaf ticket must pass verification before its PR can merge.

### Contract tickets (S5U-251, S5U-253, S5U-259, S5U-263)

```bash
make schemas          # Regenerate JSON Schema + TS types from Pydantic
make lint             # ruff check + format
make typecheck        # mypy --strict + tsc
make test             # All tests pass
uv run lint-imports   # No import cycle violations
```

**Evidence to attach:** screenshot or paste of `make schemas` diff showing new/changed schemas.

### Stage implementation tickets (S5U-252, S5U-254–S5U-258, S5U-260–S5U-262)

```bash
make lint && make typecheck && make test
uv run lint-imports
```

Plus: run the pipeline on at least one fixture PDF and verify the new stage artifact is emitted:
```bash
uv run aeon-pipeline run --doc <fixture> --stages <stage_range>
```

**Evidence to attach:** relevant stage artifact snippet or overlay for a fixture page.

### Test tickets (S5U-276, S5U-277, S5U-278, S5U-279, S5U-280, S5U-290)

```bash
make lint && make typecheck && make test
```

The new tests themselves are the verification. Confirm they run and either pass (for validation suites) or fail meaningfully on known-bad inputs (for regression harnesses).

**Evidence to attach:** pytest output showing new test names and pass/fail status.

### Review/debug tooling tickets (S5U-264, S5U-265)

```bash
make lint && make typecheck && make test
```

Plus: produce at least one overlay or golden artifact from a fixture run and verify it is inspectable.

**Evidence to attach:** sample overlay image or golden diff output.

---

## 4. Migration constraints

These constraints are **non-negotiable** during the Architecture 3 migration:

1. **Legacy path stays runnable.** The existing `extract_primitives → normalize_layout → resolve_assets_symbols → ...` path must continue to work until S5U-265 exit criteria pass. Do not delete, break, or bypass legacy stages.

2. **New path runs beside legacy.** Architecture 3 stages should be additive — invoked via explicit mode, flag, or stage range. They must not replace the legacy path until golden comparison proves equivalence or improvement.

3. **Contract changes require full regeneration.** Any Pydantic model change requires `make schemas` and a check that downstream TS types still compile. Never commit a model change without regenerated schemas.

4. **Import boundaries are enforced.** `uv run lint-imports` must pass. The import contract (models ↛ stages, llm ↛ stages, etc.) applies to new Architecture 3 code equally.

5. **No silent fallback removal.** Existing fallback/compatibility behavior (e.g., `render_mode` routing, patch application) must not be removed until a replacement is verified by tests on hard-page fixtures.

6. **Fixture expectations are stable.** Do not change fixture expected outputs in the same PR that changes the code producing those outputs. If a fixture expectation needs updating, that change goes in a separate evaluation ticket or is explicitly called out in the PR.

---

## 5. Escalation rules

Stop and escalate (comment on the Linear issue, do not improvise) when:

- A ticket's acceptance criteria are ambiguous or contradictory
- A prerequisite ticket is not complete but the issue description assumes it is
- A legacy stage needs breaking changes to accommodate the new path
- A fixture PDF does not cover the scenario the ticket needs to verify
- A contract change cascades into more than 3 downstream files unexpectedly
- `make test` failures are in unrelated code and cannot be resolved locally
- The ticket requires adding a new external dependency

Escalation means: set the issue status to **Blocked**, add a comment explaining the blocker, and move to a different ready ticket.

---

## 6. Quick reference — issue dependency graph

```
Phase 1: Evidence Contracts
  S5U-251 ──→ S5U-253 ──→ S5U-252
  S5U-251 ──→ S5U-276

Phase 2: Page Topology
  [Phase 1] ──→ S5U-254 ──→ S5U-255 ──→ S5U-256

Phase 3: Visual Assets & Entities
  [Phase 2] ──→ S5U-257 ──→ S5U-258 ──→ S5U-259
                 │                        S5U-258 ──→ S5U-277
                 └──→ S5U-260
  S5U-255 ──→ S5U-261
  S5U-255 ──→ S5U-262

Phase 4: Hard-Page Rollout
  [Phase 3] ──→ S5U-263 ──→ S5U-278 ──→ S5U-265 ──→ S5U-290
                 │                                    S5U-265 ──→ S5U-279
                 ├──→ S5U-264
                 └──→ S5U-280
```
