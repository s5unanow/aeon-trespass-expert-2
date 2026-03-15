. Architecture sanity check

Only the items below are blockers or high-risk ambiguities that should be closed before agents start implementing.

1.1 Missing formal contracts

These were implied in the architecture but not fully locked as concrete models. They need first-class schemas before most work starts:

ModelProfile

RuleProfile

SymbolPack

GlossaryPack

PatchSet

ResolvedRunPlan

RunManifest

StageManifest

ExtractedPage

TranslationUnit

TranslationResult

NavigationTree

SiteBundleManifest

BundlePage

CatalogManifest

ReleaseManifest

1.2 Public bundle boundary was not explicit enough

The frontend must not consume internal pipeline artifacts directly.
Lock this boundary:

internal pipeline canonical artifact: PageRecord

public reader artifact: BundlePage

transport boundary: 11_export/site_bundle/**

local frontend input directory: apps/reader/generated/**

1.3 apply_safe_fixes needs an operational mode

The architecture included the stage, but the release-path semantics need to be locked.

Implementation assumption to remove ambiguity:

stage always exists

in early v1 it runs in pass-through + suggestion mode

if safe fixers are enabled later, the stage must validate touched pages before export

export_site_bundle always reads from 10_fix/pages/**, even if unchanged

1.4 Contract generation direction must be fixed

Lock the single direction:

Python Pydantic models are authoritative

JSON Schema is generated from Python

TypeScript types are generated from JSON Schema

no manually maintained duplicate TS domain shapes

1.5 Sync boundary between pipeline and reader must be explicit

The frontend must not read from arbitrary run directories.

Lock this flow:

pipeline writes canonical public bundle to artifacts/runs/<run_id>/<doc_id>/11_export/site_bundle/**

sync command copies selected bundle(s) into apps/reader/generated/**

reader build reads only apps/reader/generated/**

1.6 Hybrid / facsimile fallback must be first-class

This is not optional. Some pages or blocks will be too layout-heavy to semantically reconstruct with high confidence.

Lock:

page-level render_mode

block-level fallback asset support

QA rules must understand fallback mode

frontend renderer must support fallback mode without special-case hacks

2. Final implementation assumptions
hese assumptions are locked for implementation unless an ADR explicitly changes them.

2.1 Runtime and toolchain

Backend runtime: Python 3.12

Python package/tool runner: uv

Frontend runtime: Node 22.x

Package manager: pnpm 10

Frontend framework: Next.js 15 App Router

UI runtime: React 19

Frontend language: TypeScript 5.x

2.2 Backend stack

CLI: Typer

Contracts/validation: Pydantic v2

JSON/YAML IO: orjson, PyYAML

PDF extraction: PyMuPDF

Prompt templating: Jinja2

Logging: structlog

Telemetry hooks: OpenTelemetry

LLM provider SDK: Google Gen AI Python SDK

Testing: pytest

Typing: mypy

Linting/formatting: ruff

2.3 Frontend stack

Static app: Next.js static export

Styling: CSS Modules + CSS custom properties

State: React context + reducer

Search: Pagefind

Frontend unit/component tests: Vitest + React Testing Library

E2E/visual regression: Playwright

2.4 Repo shape

Single monorepo with these stable roots:

apps/reader — static reader app

packages/pipeline — content compiler

packages/contracts — generated JSON Schema + TS types

configs — authored manifests/profiles/packs

prompts — versioned prompt bundles

tests — fixtures + backend + frontend + e2e + visual

artifacts — run outputs, cache, releases, state

docs — ADRs, specs, operator docs

scripts — generation/sync/build helpers

sources — real PDFs, gitignored

2.5 Storage and artifacts

Primary source of truth for runtime artifacts: filesystem

No primary database in v1

Canonical run root:

artifacts/runs/<run_id>/<doc_id>/

Shared cache root:

artifacts/cache/<stage>/<cache_key>/

State pointers:

artifacts/state/accepted_runs.json

artifacts/state/baselines.json

artifacts/state/releases.json

2.6 Contract strategy

Pydantic models are the only authoritative runtime contracts

JSON Schema is generated and checked into git

TS types are generated and checked into git

Any contract change requires:

model update

schema regeneration

TS regeneration

tests updated

ADR only if the change is architectural

2.7 Config strategy

All behavior lives in repo config, not env vars.

Single sources of truth:

documents: configs/documents/*.yaml

model profiles: configs/model-profiles/*.yaml

rule profiles: configs/rule-profiles/*.yaml

symbol packs: configs/symbol-packs/*.yaml

glossary packs: configs/glossary-packs/*.yaml

overrides/patches: configs/overrides/*.yaml

document catalog: configs/catalog.yaml

2.8 Public frontend data boundary

internal pipeline artifact: PageRecord

exported reader artifact: BundlePage

frontend imports only from apps/reader/generated/**

frontend does not read artifacts/runs/**

2.9 Frontend strategy

content routes are statically generated

reader pages are rendered from typed JSON bundle data

no markdown parser in the runtime reader path

no runtime regex-based content repair

no runtime glossary linking

no runtime symbol resolution

Server Components by default

client components only for interactive shells:

search dialog

theme toggle

glossary drawer

figure lightbox

sidebar collapse state

2.10 Search strategy

canonical search artifact: SearchDocument

production search index: Pagefind built from static HTML

search JS loaded lazily

no external search service in v1

2.11 Translation strategy

only text-bearing inline nodes are translated by LLM

structure, layout, assets, symbols, navigation, and rendering remain deterministic

translation memory in v1 is exact-match reuse from cached/accepted translation results

there is no separate editable TM app in v1

2.12 Testing strategy

fixture PDFs are checked in under tests/fixtures/pdf

frontend can be tested against checked-in fixture bundles under tests/fixtures/site-bundles

live LLM tests are non-blocking for normal PR CI

all core contracts, stages, and rendering modules require automated tests

2.13 Deployment assumptions

static output target: apps/reader/out

search index target: apps/reader/out/pagefind

hosting target: Cloudflare Pages

preview deploys from CI

production deploy only from accepted run + release workflow

2.14 Non-goals in v1

no OCR fallback

no CMS

no admin dashboard

no microservices

no Airflow/Prefect/Dagster

no Elasticsearch/Algolia/Meilisearch

no database as source of truth
3. Epic breakdown
EP-001 — Workspace, toolchain, and contract foundation

Objective: create the monorepo, toolchains, package boundaries, and first authoritative contracts.

Why it exists: every later epic depends on a stable repo layout and generated contract pipeline.

Dependencies: none.

Main deliverables: root workspace files, pipeline package scaffold, reader app scaffold, contracts package scaffold, local dev commands, base model set.

Acceptance criteria: fresh clone boots with one command; contracts generate; sample model round-trip tests pass.

Risks: agents manually editing generated contract files; inconsistent tooling across packages.

Parallelizable: partially.

EP-002 — Config system, artifact runtime, and stage framework

Objective: implement config packs, artifact IO, manifests, stage registry, cache layout, and CLI.

Why it exists: without this, stage work turns into ad hoc scripts and hidden conventions.

Dependencies: EP-001.

Main deliverables: config loaders, ArtifactStore, RunManifest, StageManifest, cache keys, runner, CLI.

Acceptance criteria: no-op and stub stages run/resume cleanly; artifact paths are deterministic.

Risks: path drift, implicit stage behavior, hidden mutable state.

Parallelizable: partially.

EP-003 — Source ingest and primitive extraction

Objective: hash PDFs, capture source metadata, and extract per-page primitives and raw assets.

Why it exists: this is the deterministic base layer for everything downstream.

Dependencies: EP-002.

Main deliverables: DocumentManifest, ExtractedPage, raw asset extraction, source provenance refs.

Acceptance criteria: fixture PDFs ingest and extract reproducibly with stable outputs.

Risks: PDF edge cases, unstable extraction assumptions.

Parallelizable: limited.

EP-004 — Canonical IR normalization and asset/symbol resolution

Objective: convert extracted primitives into stable semantic page records and resolved assets/symbols.

Why it exists: this is the core quality layer that replaces string-first processing.

Dependencies: EP-003.

Main deliverables: PageRecord, stable IDs/fingerprints, normalization rules, Asset records, symbol resolution, hybrid fallback support.

Acceptance criteria: representative fixture pages normalize into expected block trees.

Risks: ambiguous layout classification, overfitting heuristics.

Parallelizable: limited.

EP-005 — Translation planning and execution

Objective: add bounded LLM translation using structured units, validation, caching, and reproducibility.

Why it exists: translation is the only LLM-heavy stage and must be tightly constrained.

Dependencies: EP-004.

Main deliverables: TranslationUnit, TranslationResult, planner, glossary placeholder freezer, LlmGateway, provider adapter, retry/cache logic.

Acceptance criteria: translation results validate strictly; no placeholder corruption on fixtures.

Risks: provider drift, schema-valid but semantically bad outputs.

Parallelizable: moderate after contracts are fixed.

EP-006 — Localization merge, navigation, glossary, and search docs

Objective: merge translations into the IR and derive localized navigation/search/glossary artifacts.

Why it exists: this turns translated units into reader-usable content.

Dependencies: EP-005.

Main deliverables: localized pages, navigation tree, glossary annotations, SearchDocuments, doc summary metadata.

Acceptance criteria: sample localized bundle is internally consistent and navigable.

Risks: anchor collisions, glossary over-linking, mixed-language leakage.

Parallelizable: moderate.

EP-007 — QA, safe fixes, reports, and baselines

Objective: implement machine-readable QA, acceptance logic, regression diffing, and safe-fix scaffolding.

Why it exists: quality must be measurable and release-gated.

Dependencies: EP-006.

Main deliverables: QAIssue, rule engine, summaries/deltas, reports, baseline state, safe-fix stage.

Acceptance criteria: fixture bundles yield deterministic issue sets; gating logic is testable.

Risks: flaky rules, issue fingerprint instability.

Parallelizable: moderate.

EP-008 — Site bundle export and build/deploy bridge

Objective: export public bundle artifacts and bridge them into the reader build and release path.

Why it exists: the frontend boundary must be explicit and stable.

Dependencies: EP-007.

Main deliverables: SiteBundleManifest, BundlePage, sync command, reader build wrapper, search index wrapper, release manifest.

Acceptance criteria: reader can build from exported fixture bundle without touching internal artifacts.

Risks: public/internal contract leakage, asset path mismatch.

Parallelizable: moderate.

EP-009 — Reader frontend core

Objective: implement the static reader shell and deterministic content renderer.

Why it exists: the exported bundle needs a thin, robust reader, not a repair engine.

Dependencies: EP-008 for real bundle shape, EP-001 for scaffold.

Main deliverables: route structure, loaders, app shell, doc layout, page renderer, glossary route, catalog route.

Acceptance criteria: reader renders fixture bundle statically with no runtime content repair.

Risks: accidental over-hydration, hidden runtime parsing.

Parallelizable: high once public bundle contract exists.

EP-010 — Search, accessibility, performance, and resilience

Objective: add Pagefind search, navigation ergonomics, error boundaries, figure UX, and hardening.

Why it exists: this makes the reader production-shaped without changing core architecture.

Dependencies: EP-009.

Main deliverables: search dialog, lazy Pagefind adapter, TOC/sidebar behavior, page prefetching, lightbox, error boundaries, accessibility improvements.

Acceptance criteria: keyboard navigation, search, theme, and error containment work on fixture bundle.

Risks: client bundle creep, brittle dialog/lightbox behavior.

Parallelizable: high.

EP-011 — Test harness, CI/CD, deployment, and multi-document hardening

Objective: complete fixture corpora, end-to-end testing, CI gates, preview/release workflows, and second-document proof.

Why it exists: this converts a design into an operable system.

Dependencies: all earlier epics.

Main deliverables: backend golden tests, frontend component tests, e2e, visual tests, GitHub Actions, preview deploy, production release flow, second-document onboarding path.

Acceptance criteria: CI reliably gates regressions; second document can be added through config + bundle generation.

Risks: slow CI, baseline churn, deployment path drift.

Parallelizable: moderate.
4. Story / task breakdown per epic
EP-001 — Workspace, toolchain, and contract foundation
T001-01 — Create root workspace and package boundaries

Purpose: establish the monorepo skeleton and root toolchain files.

Files/folders: Makefile, pyproject.toml, package.json, pnpm-workspace.yaml, .python-version, .nvmrc, .gitignore, README.md

Required inputs: locked stack assumptions, repo skeleton

Outputs/artifacts produced: bootable workspace

Dependencies: none

Implementation notes: root commands must delegate to package-local tools; do not hide logic in random shell scripts

Validation steps: make bootstrap, make help

Definition of done: fresh clone installs Python and Node deps with documented commands

T001-02 — Scaffold packages/pipeline

Purpose: create installable backend package and initial module layout.

Files/folders: packages/pipeline/pyproject.toml, packages/pipeline/src/aeon_reader_pipeline/**

Required inputs: repo boundary rules

Outputs/artifacts produced: importable package with placeholder modules

Dependencies: T001-01

Implementation notes: create directories for cli, models, stages, io, cache, config, llm, qa, migrations

Validation steps: uv run python -c "import aeon_reader_pipeline"

Definition of done: package imports cleanly and exposes version/module root

T001-03 — Scaffold packages/contracts and apps/reader

Purpose: create the generated contracts package and reader app workspace.

Files/folders: packages/contracts/**, apps/reader/**

Required inputs: public bundle boundary assumption

Outputs/artifacts produced: empty contracts package, buildable Next app scaffold

Dependencies: T001-01

Implementation notes: packages/contracts must be consumable as a workspace package by apps/reader

Validation steps: pnpm --filter reader lint, pnpm --filter reader build

Definition of done: reader app builds with placeholder routes and imports a placeholder contracts package

T001-04 — Add local quality tooling and smoke tests

Purpose: make basic correctness checks available before feature work.

Files/folders: root lint/type configs, tests/backend/test_smoke.py, tests/frontend/*.test.tsx

Required inputs: package scaffolds

Outputs/artifacts produced: local lint, typecheck, smoke-test commands

Dependencies: T001-02, T001-03

Implementation notes: keep initial tests trivial but executable; avoid waiting for full features

Validation steps: make lint, make typecheck, make test

Definition of done: baseline quality commands run on CI-ready scaffolds

EP-002 — Config system, artifact runtime, and stage framework
T002-01 — Define config pack models and loaders

Purpose: formalize authored config schemas and load/validate them.

Files/folders: packages/pipeline/src/aeon_reader_pipeline/models/config_models.py, config/loader.py, configs/**

Required inputs: config assumptions, contract list

Outputs/artifacts produced: DocumentConfig, ModelProfile, RuleProfile, SymbolPack, GlossaryPack, PatchSet, CatalogConfig

Dependencies: EP-001

Implementation notes: YAML in, Pydantic out; no stage may read raw YAML directly

Validation steps: pytest tests/backend/test_config_loader.py

Definition of done: all sample configs load into typed models with deterministic validation errors

T002-02 — Implement artifact store and JSON/JSONL IO

Purpose: centralize all reading/writing of versioned artifacts.

Files/folders: io/json_io.py, io/artifact_store.py, tests/backend/test_artifact_store.py

Required inputs: artifact directory conventions

Outputs/artifacts produced: safe JSON/JSONL readers/writers, canonical path helpers

Dependencies: T001-02

Implementation notes: all writers must atomically write temp file then move; all reads validate against model

Validation steps: pytest tests/backend/test_artifact_store.py

Definition of done: artifacts can be written/read/validated without ad hoc filesystem code elsewhere

T002-03 — Define run/state manifests and cache keys

Purpose: formalize run metadata, stage metadata, state pointers, and cache addressing.

Files/folders: models/run_models.py, cache/keys.py, io/state_store.py

Required inputs: run directory layout, cache strategy

Outputs/artifacts produced: PipelineConfig, ResolvedRunPlan, RunManifest, StageManifest, state JSON handlers

Dependencies: T002-02

Implementation notes: cache keys must include stage version + relevant input hashes; state files live outside runs

Validation steps: pytest tests/backend/test_run_models.py tests/backend/test_cache_keys.py

Definition of done: run metadata and state pointer files are fully typed and test-covered

T002-04 — Build stage base classes, registry, runner, and CLI

Purpose: create the execution framework for all later stages.

Files/folders: stage_framework/base.py, stage_framework/registry.py, stage_framework/runner.py, cli/main.py

Required inputs: stage naming and ordering

Outputs/artifacts produced: runner with run, resume, inspect, list-stages

Dependencies: T002-01, T002-02, T002-03

Implementation notes: stages receive typed config/context, never raw CLI args; stage runner owns manifest updates

Validation steps: pytest tests/backend/test_runner.py; uv run reader-pipeline list-stages

Definition of done: stub stages run in order and resume works on a toy pipeline

EP-003 — Source ingest and primitive extraction
T003-01 — Implement ingest_source

Purpose: produce immutable DocumentManifest from a source PDF.

Files/folders: models/manifest_models.py, stages/ingest_source.py, tests/backend/test_ingest_source.py

Required inputs: source path, DocumentConfig

Outputs/artifacts produced: 01_ingest/document_manifest.json

Dependencies: EP-002

Implementation notes: capture PDF hash, size, page count, metadata, page dimensions, source outline

Validation steps: fixture ingest test over tiny PDF

Definition of done: fixture PDF produces stable manifest across repeated runs

T003-02 — Define ExtractedPage and extract text primitives

Purpose: formalize the raw extracted page contract and populate it from PyMuPDF.

Files/folders: models/extract_models.py, stages/extract_primitives.py

Required inputs: DocumentManifest, source PDF

Outputs/artifacts produced: 02_extract/pages/p0001.json etc.

Dependencies: T003-01

Implementation notes: include blocks/lines/spans, fonts, bbox, page size, source refs; do not infer semantics here

Validation steps: pytest tests/backend/test_extract_primitives.py

Definition of done: extracted pages validate against schema and contain reproducible primitive structure

T003-03 — Extract raw assets and source references

Purpose: persist raw page assets and link them to source page coordinates/references.

Files/folders: stages/extract_primitives.py, models/extract_models.py, tests/backend/test_extract_assets.py

Required inputs: PyMuPDF page objects

Outputs/artifacts produced: 02_extract/assets/raw/**, asset refs in ExtractedPage

Dependencies: T003-02

Implementation notes: do not create final derivatives here; just extract and hash raw resources

Validation steps: asset extraction test against fixture with image/vector content

Definition of done: raw assets exist with hashes and page associations

T003-04 — Add extraction fixture corpus and goldens

Purpose: freeze expected extraction output on representative pages.

Files/folders: tests/fixtures/pdf/**, tests/backend/goldens/extract/**, tests/backend/test_extract_goldens.py

Required inputs: tiny fixture PDFs with text, lists, figures, tables

Outputs/artifacts produced: golden extracted artifacts

Dependencies: T003-02, T003-03

Implementation notes: use synthetic or licensed small fixtures; do not commit copyrighted source rulebook PDFs

Validation steps: pytest tests/backend/test_extract_goldens.py

Definition of done: extraction regressions are caught by golden tests
EP-004 — Canonical IR normalization and asset/symbol resolution
T004-01 — Define IR models, stable IDs, and normalization helpers

Purpose: create PageRecord, Block, InlineNode, Asset, PageAnchor, fingerprinting rules.

Files/folders: models/ir_models.py, utils/ids.py, utils/normalization.py

Required inputs: extracted page contract

Outputs/artifacts produced: core IR models and helper functions

Dependencies: EP-002, EP-003

Implementation notes: dual identity model: readable IDs + content fingerprints

Validation steps: pytest tests/backend/test_ir_models.py tests/backend/test_ids.py

Definition of done: IR models support discriminated unions and stable ID/fingerprint generation

T004-02 — Implement normalize_layout

Purpose: turn ExtractedPage into source-side semantic PageRecord.

Files/folders: stages/normalize_layout.py, qa/rules/layout_helpers.py, tests/backend/test_normalize_layout.py

Required inputs: ExtractedPage, RuleProfile, optional PatchSet

Outputs/artifacts produced: 03_normalize/pages/p0001.json

Dependencies: T004-01

Implementation notes: detect headings, paragraphs, lists, callouts, figures, captions, tables; do not localize yet

Validation steps: normalization tests on representative fixtures

Definition of done: expected fixture pages normalize into correct block kinds and order

T004-03 — Implement symbol packs and asset resolution

Purpose: resolve canonical symbols and asset relationships.

Files/folders: config/symbol_loader.py, stages/resolve_assets_symbols.py, models/asset_models.py

Required inputs: normalized pages, extracted assets, SymbolPack

Outputs/artifacts produced: 04_assets/pages/**, 04_assets/assets/*.json

Dependencies: T004-02

Implementation notes: attach figure/caption links, inline symbol nodes, render policies, asset anchors

Validation steps: pytest tests/backend/test_symbol_resolution.py tests/backend/test_asset_resolution.py

Definition of done: symbols resolve from one canonical pack and unresolved cases become explicit issues

T004-04 — Implement patch/override layer and hybrid fallback handling

Purpose: provide deterministic escape hatches for ambiguous pages and blocks.

Files/folders: config/patch_loader.py, stages/normalize_layout.py, stages/resolve_assets_symbols.py, tests/backend/test_patches.py

Required inputs: PatchSet schema, fallback policy

Outputs/artifacts produced: patched normalized pages, hybrid/fallback flags

Dependencies: T004-02, T004-03

Implementation notes: patches must be declarative, idempotent, and provenance-tagged

Validation steps: patch tests against synthetic ambiguous fixtures

Definition of done: overrides can correct known pages without ad hoc code edits

EP-005 — Translation planning and execution
T005-01 — Define translation contracts and planner

Purpose: formalize TranslationUnit and group text-bearing nodes into bounded units.

Files/folders: models/translation_models.py, stages/plan_translation.py, tests/backend/test_translation_planner.py

Required inputs: localized target locale, source-side PageRecord, glossary pack

Outputs/artifacts produced: 05_translation_plan/units/*.json

Dependencies: EP-004

Implementation notes: preserve non-text nodes; unit grouping by semantic locality, not whole page

Validation steps: planner tests confirm stable unit IDs and bounded sizes

Definition of done: planner outputs deterministic units with exact inline ID coverage

T005-02 — Implement glossary locking, placeholders, and exact-match reuse

Purpose: protect locked terms and skip unnecessary LLM calls.

Files/folders: llm/placeholders.py, llm/translation_memory.py, tests/backend/test_placeholders.py

Required inputs: TranslationUnit, glossary rules, prior accepted results/cache

Outputs/artifacts produced: placeholder maps, TM hit records, preprocessed units

Dependencies: T005-01

Implementation notes: v1 translation memory is exact-match reuse only; no fuzzy TM

Validation steps: tests for placeholder round-trip and exact cache hit behavior

Definition of done: locked terms survive preprocessing and restoration exactly

T005-03 — Implement LlmGateway, provider adapter, and result validator

Purpose: isolate provider-specific calls and enforce strict result validation.

Files/folders: llm/base.py, llm/gemini.py, llm/prompts.py, llm/validation.py

Required inputs: TranslationUnit, prompt bundle, model profile

Outputs/artifacts produced: validated TranslationResult, raw call metadata

Dependencies: T005-01, T005-02

Implementation notes: stage code must talk only to LlmGateway; validation rejects missing IDs, extras, corrupted placeholders, glossary violations

Validation steps: pytest tests/backend/test_llm_validation.py

Definition of done: mocked provider and bad-response tests cover all rejection paths

T005-04 — Implement translate_units with retry, cache, and benchmark harness

Purpose: execute real unit translation with resumability and reproducibility.

Files/folders: stages/translate_units.py, cache/keys.py, benchmarks/translate/**, tests/backend/test_translate_units.py

Required inputs: planned units, LLM gateway, cache policy

Outputs/artifacts produced: 06_translate/results/*.json, 06_translate/calls/*.json, 06_translate/failures/*.json

Dependencies: T005-03

Implementation notes: retries are unit-scoped; fallback model optional via profile; persist provider/model/prompt metadata

Validation steps: mocked execution tests, resume tests, cache hit tests

Definition of done: translated units can be resumed and audited unit-by-unit

EP-006 — Localization merge, navigation, glossary, and search docs
T006-01 — Implement merge_localization

Purpose: merge validated translations back into exact inline slots in PageRecord.

Files/folders: stages/merge_localization.py, tests/backend/test_merge_localization.py

Required inputs: 04_assets/pages/**, 06_translate/results/**, glossary pack

Outputs/artifacts produced: 07_localize/pages/*.json

Dependencies: EP-005

Implementation notes: keep source inlines, add localized inlines by locale key; reject partial or mismatched merges

Validation steps: tests for missing units, placeholder restoration, leakage detection

Definition of done: localized pages validate and preserve original structure exactly

T006-02 — Add glossary annotations and localized asset labels

Purpose: attach deterministic glossary hits and public-facing labels to content.

Files/folders: stages/merge_localization.py, utils/glossary_linker.py, tests/backend/test_glossary_annotations.py

Required inputs: localized pages, glossary pack, symbol/asset labels

Outputs/artifacts produced: glossary hit annotations within localized pages

Dependencies: T006-01

Implementation notes: no regex runtime linking in frontend; all linkability is precomputed here

Validation steps: glossary linker tests with Russian variants and first-only/always policies

Definition of done: glossary hits are deterministic and test-covered

T006-03 — Build navigation, search docs, and document metadata

Purpose: derive reader navigation and search inputs from localized pages.

Files/folders: stages/enrich_content.py, models/build_models.py, tests/backend/test_enrich_content.py

Required inputs: localized pages, document manifest, document config

Outputs/artifacts produced: 08_enrich/navigation.json, 08_enrich/search_documents.jsonl, 08_enrich/doc_summary.json

Dependencies: T006-01

Implementation notes: anchor IDs must be deterministic; duplicate anchors are errors

Validation steps: tests for heading path generation, anchor uniqueness, search doc coverage

Definition of done: navigation and search docs are stable and internally consistent

T006-04 — Add localized integration fixtures

Purpose: freeze end-to-end localized artifact examples for later frontend and QA work.

Files/folders: tests/fixtures/localized/**, tests/backend/test_localized_goldens.py

Required inputs: small translated fixture outputs

Outputs/artifacts produced: goldens for 07_localize and 08_enrich

Dependencies: T006-01, T006-03

Implementation notes: use controlled fixtures; keep them small and reviewable

Validation steps: golden comparison tests

Definition of done: localized bundle regressions are caught before frontend work
EP-007 — QA, safe fixes, reports, and baselines
T007-01 — Define QA contracts and rule engine

Purpose: formalize QAIssue and create a pure rule execution framework.

Files/folders: models/qa_models.py, qa/engine.py, qa/rules/__init__.py, tests/backend/test_qa_engine.py

Required inputs: localized pages, navigation, search docs

Outputs/artifacts produced: rule engine API and issue schemas

Dependencies: EP-006

Implementation notes: rule functions must be side-effect free; issue location granularity must support document/page/block/inline/asset

Validation steps: unit tests on synthetic rule inputs

Definition of done: rules emit fully typed issues with stable fingerprints

T007-02 — Implement core rules and acceptance summary

Purpose: add the first release-blocking and warning rule packs.

Files/folders: qa/rules/schema_rules.py, layout_rules.py, translation_rules.py, symbol_rules.py, render_rules.py, stages/evaluate_qa.py

Required inputs: localized artifacts, rule profile, optional baseline

Outputs/artifacts produced: 09_qa/issues.jsonl, 09_qa/summary.json

Dependencies: T007-01

Implementation notes: keep thresholds in rule profile, never in functions; acceptance logic centralized in summary builder

Validation steps: pytest tests/backend/test_qa_rules.py

Definition of done: fixture bundles yield deterministic summaries and pass/fail states

T007-03 — Implement baseline deltas and derived reports

Purpose: compare runs and produce human-readable views from JSON QA artifacts.

Files/folders: qa/reports.py, io/state_store.py, tests/backend/test_qa_delta.py

Required inputs: current issues, baseline ref, state pointers

Outputs/artifacts produced: 09_qa/delta.json, 09_qa/report.md, 09_qa/report.html

Dependencies: T007-02

Implementation notes: markdown/html are derived only; issue fingerprints drive delta computation

Validation steps: delta tests with synthetic new/resolved/regressed cases

Definition of done: baseline comparison works without parsing human-readable reports

T007-04 — Implement apply_safe_fixes in pass-through + suggestion mode

Purpose: establish the safe-fix stage without destabilizing v1.

Files/folders: stages/apply_safe_fixes.py, models/patch_models.py, tests/backend/test_apply_safe_fixes.py

Required inputs: localized pages, QA issues, patch set

Outputs/artifacts produced: 10_fix/pages/*.json, 10_fix/suggestions.jsonl, 10_fix/validation.json

Dependencies: T007-02

Implementation notes: v1 default behavior is copy-forward + patch suggestions; later safe fixers must revalidate touched pages

Validation steps: stage pass-through tests and fix suggestion tests

Definition of done: export can always read 10_fix/pages/** and fix stage is deterministic

EP-008 — Site bundle export and build/deploy bridge
T008-01 — Define public bundle contracts and exporter

Purpose: formalize the frontend-facing bundle and export from final pipeline artifacts.

Files/folders: models/site_bundle_models.py, stages/export_site_bundle.py, tests/backend/test_export_site_bundle.py

Required inputs: fixed pages, navigation, glossary index, assets, doc summary

Outputs/artifacts produced: 11_export/site_bundle/<doc_id>/**, 11_export/build_artifacts.json

Dependencies: EP-007

Implementation notes: exported bundle should strip internal-only fields and preserve stable public file paths

Validation steps: schema validation plus snapshot tests of exported bundle shape

Definition of done: a reader can consume exported bundle without accessing internal artifacts

T008-02 — Implement bundle sync into apps/reader/generated

Purpose: make the frontend build path explicit and local.

Files/folders: scripts/sync_generated_bundle.py, apps/reader/generated/.gitignore, tests/backend/test_sync_bundle.py

Required inputs: exported bundle path, selected run/doc IDs

Outputs/artifacts produced: synced apps/reader/generated/**

Dependencies: T008-01

Implementation notes: sync should copy only selected docs; wipe target doc folder before sync

Validation steps: sync test plus local reader build against synced fixture bundle

Definition of done: buildable generated input exists under one stable reader path

T008-03 — Implement build_reader and index_search wrappers

Purpose: integrate frontend static build and Pagefind indexing into the pipeline.

Files/folders: stages/build_reader.py, stages/index_search.py, scripts/build_reader.mjs, scripts/index_search.mjs

Required inputs: synced bundle, reader app source

Outputs/artifacts produced: 12_site/out/**, 13_search/pagefind/**

Dependencies: T008-02

Implementation notes: wrappers may shell out to pnpm; pipeline must still record manifests and failures

Validation steps: reader build smoke test, Pagefind smoke query test

Definition of done: one command produces static HTML and search index from the exported bundle

T008-04 — Implement package_release and release manifest

Purpose: package accepted artifacts and record deployable release metadata.

Files/folders: stages/package_release.py, models/release_models.py, tests/backend/test_package_release.py

Required inputs: QA acceptance, built site, indexed search, deployment target config

Outputs/artifacts produced: 14_release/release_manifest.json, deployable package directory

Dependencies: T008-03

Implementation notes: package stage does not decide acceptance; it enforces it

Validation steps: mocked release packaging tests with accepted vs rejected runs

Definition of done: release packaging is gated, typed, and auditable

EP-009 — Reader frontend core
T009-01 — Implement typed bundle loaders and route params

Purpose: make reader routes consume generated bundle data safely.

Files/folders: apps/reader/lib/bundle.ts, lib/routes.ts, app/docs/[docId]/page/[pageNo]/page.tsx, packages/contracts/typescript/**

Required inputs: SiteBundleManifest, BundlePage, CatalogManifest

Outputs/artifacts produced: typed filesystem loaders and route param helpers

Dependencies: T008-01

Implementation notes: loaders run at build time/server side only; no client fetches for core page content

Validation steps: pnpm --filter reader test, route param tests

Definition of done: routes statically resolve valid docs/pages from generated bundle

T009-02 — Implement app shell, document layout, and theme

Purpose: provide the shared layout for catalog and document routes.

Files/folders: app/layout.tsx, components/AppShell.tsx, components/DocLayout.tsx, components/ThemeProvider.tsx, styles/theme.css

Required inputs: route structure, minimal design tokens

Outputs/artifacts produced: shared shell, theme system, top-level layout

Dependencies: T009-01

Implementation notes: keep shell thin; theme state is one small client boundary

Validation steps: component tests + static build

Definition of done: shell renders with both light/dark themes and stable layout structure

T009-03 — Implement page renderer and block/inline components

Purpose: render bundle page content deterministically from typed unions.

Files/folders: components/PageView.tsx, components/BlockRenderer.tsx, components/InlineRenderer.tsx, block-specific components

Required inputs: BundlePage block/inline unions

Outputs/artifacts produced: semantic HTML page rendering

Dependencies: T009-01

Implementation notes: exhaustive switch with assertNever; no markdown, no HTML injection

Validation steps: component tests over fixture bundle pages

Definition of done: all supported block kinds render and unknown kinds fail explicitly in tests
T009-04 — Implement catalog, document landing, and glossary routes

Purpose: complete the basic reader information architecture.

Files/folders: app/page.tsx, app/docs/[docId]/page.tsx, app/docs/[docId]/glossary/page.tsx, related components

Required inputs: CatalogManifest, doc summary bundle, glossary bundle

Outputs/artifacts produced: catalog page, document landing page, glossary page

Dependencies: T009-02

Implementation notes: keep glossary route static and server-rendered

Validation steps: route tests and static build

Definition of done: catalog and glossary routes work from generated bundle only

EP-010 — Search, accessibility, performance, and resilience
T010-01 — Implement Pagefind search dialog adapter

Purpose: add search without bloating the initial bundle.

Files/folders: components/SearchDialog.tsx, lib/pagefind.ts, tests/frontend/SearchDialog.test.tsx

Required inputs: built Pagefind index, route helpers

Outputs/artifacts produced: lazy search dialog and result navigation

Dependencies: EP-009, T008-03

Implementation notes: import Pagefind on first open; cache loaded module; default filter by active doc

Validation steps: frontend unit tests + e2e search scenario

Definition of done: search works without loading Pagefind on initial page render

T010-02 — Implement TOC/sidebar, page navigation, and prefetching

Purpose: make navigation fast and clear.

Files/folders: components/DocSidebar.tsx, components/TocTree.tsx, components/PageNav.tsx

Required inputs: navigation bundle, page route helpers

Outputs/artifacts produced: collapsible TOC, prev/next navigation, route links

Dependencies: T009-02, T009-03

Implementation notes: use static links and Next prefetch; preserve current page anchor highlighting where possible

Validation steps: component tests + e2e keyboard navigation

Definition of done: navigation works by mouse and keyboard and does not require client fetching

T010-03 — Implement figure/lightbox, symbol rendering, and error boundaries

Purpose: handle non-text content and isolate runtime failures.

Files/folders: components/FigureBlock.tsx, components/FigureLightbox.tsx, components/SymbolInline.tsx, components/RouteErrorBoundary.tsx

Required inputs: asset map, symbol map, bundle page content

Outputs/artifacts produced: figure interactions, symbol components, route/module error boundaries

Dependencies: T009-03

Implementation notes: keep lightbox a client-only leaf; route content stays server-rendered

Validation steps: component tests and injected-failure tests

Definition of done: figure UI and error isolation both work without white-screening the reader

T010-04 — Accessibility and performance hardening

Purpose: make the reader usable and production-shaped.

Files/folders: reader components, styles/**, tests/e2e/**, tests/visual/**

Required inputs: working reader pages

Outputs/artifacts produced: accessibility semantics, focus handling, reduced-motion support, visual snapshots

Dependencies: T010-01, T010-02, T010-03

Implementation notes: content remains static-first; do not add a state library or runtime parser

Validation steps: Playwright a11y smoke, visual baselines, performance smoke checks

Definition of done: reader passes defined keyboard/focus/theme/search acceptance tests

EP-011 — Test harness, CI/CD, deployment, and multi-document hardening
T011-01 — Build backend fixture corpus and integration/golden tests

Purpose: make pipeline behavior measurable and non-regressive.

Files/folders: tests/backend/**, tests/fixtures/pdf/**, tests/fixtures/site-bundles/**

Required inputs: stages through export

Outputs/artifacts produced: unit, integration, and golden tests across stages

Dependencies: EP-003 through EP-008

Implementation notes: fixture corpus must include dense text, lists, symbols, figure/caption, and fallback page

Validation steps: make test-backend

Definition of done: backend changes can be validated without running full real-doc pipeline

T011-02 — Build frontend component, e2e, and visual tests

Purpose: protect the reader against regressions.

Files/folders: tests/frontend/**, tests/e2e/**, tests/visual/**, Playwright/Vitest configs

Required inputs: working reader routes

Outputs/artifacts produced: reader component tests, e2e flows, screenshot baselines

Dependencies: EP-009, EP-010

Implementation notes: use checked-in fixture bundle for most UI tests

Validation steps: pnpm --filter reader test, pnpm --filter reader test:e2e

Definition of done: search, navigation, glossary, theme, and reader rendering are under automated test

T011-03 — Implement CI workflows and preview/release deploys

Purpose: automate validation and delivery.

Files/folders: .github/workflows/ci.yml, .github/workflows/preview.yml, .github/workflows/release.yml

Required inputs: stable commands from earlier epics

Outputs/artifacts produced: PR CI, preview deployment, gated production release

Dependencies: EP-001, EP-008, T011-01, T011-02

Implementation notes: upload failed fixture artifacts for debugging; keep live LLM tests out of default PR path

Validation steps: workflow dry run on sample branch; local command parity

Definition of done: PRs run full defined checks and main/tag flows deploy predictably

T011-04 — Add second-document hardening and operator docs

Purpose: prove the architecture is truly multi-document and operable.

Files/folders: configs/documents/<second_doc>.yaml, tests/fixtures/**, docs/operator-guides/**

Required inputs: working full pipeline and reader

Outputs/artifacts produced: second document config, multi-doc catalog validation, operator docs

Dependencies: all earlier epics

Implementation notes: second doc can be synthetic/minimal; goal is route/build/config proof, not content scale

Validation steps: multi-doc fixture build and catalog route test

Definition of done: adding another document requires config and content only, not code changes
5. Recommended implementation order
5.1 What must come first

EP-001

T002-01, T002-02, T002-03, T002-04

core contract generation pipeline

RunManifest, StageManifest, ArtifactStore

Reason: without contracts, repo layout, and stage runtime, agents will invent incompatible file paths, JSON shapes, and execution flows.

5.2 Best sequence

EP-001 — workspace and contracts foundation

EP-002 — config, manifests, runner, cache

EP-003 — ingest and extract

EP-004 — normalize and asset/symbol resolution

EP-005 — translation subsystem

EP-006 — localization and enrichment

EP-007 — QA and fix stage

EP-008 — export bundle and build bridge

EP-009 — reader core

EP-010 — search and hardening

EP-011 — full test, CI/CD, multi-doc proof

5.3 What can be parallelized

After EP-001 and the first contract set are done:

frontend scaffold work can proceed in parallel with backend stage work

packages/contracts generation and reader loader integration can proceed in parallel with extraction stages

QA report rendering can begin once QAIssue is locked, even before all rules exist

reader shell and theme can be built against fixture bundle stubs before the real exporter is finished

CI scaffolding can start early, but only basic jobs should be enabled before real fixtures exist

5.4 What should be deferred

Until after the first working localized bundle exists:

live LLM benchmark workflows

second-doc hardening

visual regression baselines beyond a small core set

any optimization beyond route-level and search lazy loading

any safe fixer that mutates content

5.5 Sequence that minimizes rework

Lock models and generated contracts early

Lock the exported public bundle before heavy frontend work

Build the English static proof before LLM integration

Add translation only after IR normalization is stable

Add QA before release packaging

Add Pagefind only after static HTML routes exist

5.6 First meaningful cut

The lowest-risk first milestone is:

ingest a fixture PDF

extract primitives

normalize to PageRecord

export a minimal English BundlePage

render it in the reader

That proves the architecture before translation complexity enters.

6. ADR list
ADR-0001 — Canonical IR is page-sharded and markdown is not canonical

Decision: PageRecord is canonical; markdown is debug/export only.

Why it matters: prevents string-first drift and frontend repair logic.

When to write: immediately

Alternatives: markdown-first pipeline, HTML-first pipeline

ADR-0002 — Pydantic owns contracts; JSON Schema and TS types are generated

Decision: Python models are authoritative; TS types are generated.

Why it matters: removes dual-schema drift.

When to write: immediately

Alternatives: hand-maintained TS types, schema-first without runtime models

ADR-0003 — Immutable filesystem artifacts and content-addressed cache

Decision: filesystem is primary artifact store; runs are immutable; cache is shared by stage key.

Why it matters: auditability, resumability, inspectability.

When to write: before EP-002

Alternatives: SQLite primary store, object store only, mutable working directories

ADR-0004 — Custom stage runner instead of workflow platform

Decision: use internal runner + manifests, not Airflow/Prefect/Dagster.

Why it matters: keeps the system solo-builder friendly and explicit.

When to write: before EP-002

Alternatives: Prefect, Dagster, shell scripts only

ADR-0005 — LLM scope is bounded to translation of text-bearing inline nodes

Decision: LLMs do not own structure, layout, or rendering.

Why it matters: this is the highest-value correctness boundary.

When to write: before EP-005

Alternatives: whole-page translation, markdown-emitting translation, layout repair by LLM

ADR-0006 — Public site bundle is distinct from internal pipeline artifacts

Decision: reader consumes exported bundle only, never internal run artifacts.

Why it matters: protects frontend from pipeline internals and reduces bundle complexity.

When to write: before EP-008

Alternatives: frontend reading PageRecord directly, frontend reading raw run dirs
ADR-0007 — Hybrid/facsimile fallback is allowed and explicit

Decision: complex pages/blocks may fall back to asset-backed rendering through contract fields.

Why it matters: avoids brittle attempts to semantically reconstruct everything.

When to write: before EP-004

Alternatives: fail the pipeline, image-only site, implicit hacks

ADR-0008 — Search is Pagefind over static HTML

Decision: Pagefind is the only search solution in v1.

Why it matters: search architecture affects export, frontend, and deploy.

When to write: before EP-008/EP-010

Alternatives: client-only MiniSearch, remote search service

ADR-0009 — Reader is Next.js static export with App Router

Decision: static export, file-based routes, Server Components by default.

Why it matters: sets the frontend data-loading and deploy model.

When to write: before EP-009

Alternatives: SPA with Vite, Astro, custom static generator

ADR-0010 — Safe-fix stage starts in pass-through + suggestion mode

Decision: v1 does not mutate content automatically except explicitly enabled safe fixers.

Why it matters: avoids premature silent content mutation.

When to write: before EP-007

Alternatives: no fix stage, always-on auto-fixes

ADR-0011 — Config packs are single sources of truth

Decision: documents, models, rules, glossary, symbols, and patches each have one canonical pack location.

Why it matters: prevents scattered constants and drift.

When to write: before EP-002

Alternatives: inline code constants, mixed JSON/TS/Python sources

ADR-0012 — Baseline QA and release gating

Decision: accepted runs and baselines are explicit state pointers; release is gated by machine-readable QA.

Why it matters: correctness must be operational, not informal.

When to write: before EP-007/EP-008

Alternatives: manual release approval only, markdown report parsing

ADR-0013 — Multi-document route and catalog scheme

Decision: root catalog route plus /docs/[docId]/... routes; doc addition via config and bundle only.

Why it matters: this locks expansion behavior.

When to write: before EP-009

Alternatives: single-doc app, locale/doc mixed routes, hash navigation only

7. Repo skeleton
/
├─ .editorconfig
├─ .gitignore
├─ .nvmrc
├─ .python-version
├─ Makefile
├─ README.md
├─ package.json
├─ pnpm-workspace.yaml
├─ pyproject.toml
│
├─ .github/
│  └─ workflows/
│     ├─ ci.yml
│     ├─ preview.yml
│     ├─ release.yml
│     └─ nightly.yml
│
├─ apps/
│  └─ reader/
│     ├─ package.json
│     ├─ next.config.ts
│     ├─ tsconfig.json
│     ├─ vitest.config.ts
│     ├─ playwright.config.ts
│     ├─ app/
│     │  ├─ layout.tsx
│     │  ├─ page.tsx
│     │  ├─ not-found.tsx
│     │  ├─ error.tsx
│     │  └─ docs/
│     │     └─ [docId]/
│     │        ├─ page.tsx
│     │        ├─ glossary/
│     │        │  └─ page.tsx
│     │        └─ page/
│     │           └─ [pageNo]/
│     │              └─ page.tsx
│     ├─ components/
│     │  ├─ AppShell.tsx
│     │  ├─ DocLayout.tsx
│     │  ├─ DocSidebar.tsx
│     │  ├─ TocTree.tsx
│     │  ├─ PageView.tsx
│     │  ├─ BlockRenderer.tsx
│     │  ├─ InlineRenderer.tsx
│     │  ├─ SymbolInline.tsx
│     │  ├─ GlossaryDrawer.tsx
│     │  ├─ SearchDialog.tsx
│     │  ├─ FigureLightbox.tsx
│     │  ├─ PageNav.tsx
│     │  └─ RouteErrorBoundary.tsx
│     ├─ lib/
│     │  ├─ bundle.ts
│     │  ├─ routes.ts
│     │  ├─ pagefind.ts
│     │  ├─ a11y.ts
│     │  └─ assertNever.ts
│     ├─ styles/
│     │  ├─ globals.css
│     │  └─ theme.css
│     ├─ generated/
│     │  └─ .gitignore
│     ├─ public/
│     │  └─ .gitkeep
│     └─ tests/
│        ├─ unit/
│        ├─ component/
│        ├─ e2e/
│        └─ visual/
│
├─ packages/
│  ├─ pipeline/
│  │  ├─ pyproject.toml
│  │  ├─ README.md
│  │  └─ src/
│  │     └─ aeon_reader_pipeline/
│  │        ├─ __init__.py
│  │        ├─ cli/
│  │        │  └─ main.py
│  │        ├─ config/
│  │        │  ├─ loader.py
│  │        │  ├─ hashing.py
│  │        │  ├─ symbol_loader.py
│  │        │  ├─ glossary_loader.py
│  │        │  └─ patch_loader.py
│  │        ├─ stage_framework/
│  │        │  ├─ base.py
│  │        │  ├─ registry.py
│  │        │  ├─ runner.py
│  │        │  └─ context.py
│  │        ├─ models/
│  │        │  ├─ base.py
│  │        │  ├─ config_models.py
│  │        │  ├─ run_models.py
│  │        │  ├─ manifest_models.py
│  │        │  ├─ extract_models.py
│  │        │  ├─ ir_models.py
│  │        │  ├─ translation_models.py
│  │        │  ├─ qa_models.py
│  │        │  ├─ site_bundle_models.py
│  │        │  └─ release_models.py
│  │        ├─ io/
│  │        │  ├─ json_io.py
│  │        │  ├─ artifact_store.py
│  │        │  └─ state_store.py
│  │        ├─ cache/
│  │        │  └─ keys.py
│  │        ├─ llm/
│  │        │  ├─ base.py
│  │        │  ├─ gemini.py
│  │        │  ├─ prompts.py
│  │        │  ├─ validation.py
│  │        │  ├─ placeholders.py
│  │        │  └─ translation_memory.py
│  │        ├─ qa/
│  │        │  ├─ engine.py
│  │        │  ├─ reports.py
│  │        │  └─ rules/
│  │        │     ├─ schema_rules.py
│  │        │     ├─ layout_rules.py
│  │        │     ├─ translation_rules.py
│  │        │     ├─ symbol_rules.py
│  │        │     ├─ render_rules.py
│  │        │     └─ search_rules.py
│  │        ├─ stages/
│  │        │  ├─ resolve_run.py
│  │        │  ├─ ingest_source.py
│  │        │  ├─ extract_primitives.py
│  │        │  ├─ normalize_layout.py
│  │        │  ├─ resolve_assets_symbols.py
│  │        │  ├─ plan_translation.py
│  │        │  ├─ translate_units.py
│  │        │  ├─ merge_localization.py
│  │        │  ├─ enrich_content.py
│  │        │  ├─ evaluate_qa.py
│  │        │  ├─ apply_safe_fixes.py
│  │        │  ├─ export_site_bundle.py
│  │        │  ├─ build_reader.py
│  │        │  ├─ index_search.py
│  │        │  └─ package_release.py
│  │        ├─ utils/
│  │        │  ├─ ids.py
│  │        │  ├─ normalization.py
│  │        │  ├─ glossary_linker.py
│  │        │  └─ hashing.py
│  │        ├─ inspect/
│  │        │  └─ page_inspector.py
│  │        └─ migrations/
│  │
│  └─ contracts/
│     ├─ package.json
│     ├─ README.md
│     ├─ jsonschema/
│     │  └─ .gitkeep
│     ├─ typescript/
│     │  ├─ src/
│     │  │  ├─ generated/
│     │  │  └─ index.ts
│     │  └─ tsconfig.json
│     └─ scripts/
│        └─ generate-types.mjs
│
├─ configs/
│  ├─ catalog.yaml
│  ├─ documents/
│  │  └─ aeon-trespass-core.yaml
│  ├─ model-profiles/
│  │  └─ translate-default.yaml
│  ├─ rule-profiles/
│  │  └─ rulebook-default.yaml
│  ├─ symbol-packs/
│  │  └─ aeon-core.yaml
│  ├─ glossary-packs/
│  │  └─ aeon-core.yaml
│  └─ overrides/
│     └─ aeon-trespass-core.yaml
│
├─ prompts/
│  ├─ translate/
│  │  └─ v1/
│  │     ├─ system.j2
│  │     ├─ input_example.json
│  │     ├─ response_schema.json
│  │     └─ README.md
│  └─ agents/
│     ├─ implement-backend-stage.md
│     ├─ implement-schema.md
│     ├─ implement-frontend-module.md
│     ├─ write-tests.md
│     ├─ write-adr.md
│     ├─ refactor-no-behavior-change.md
│     ├─ validate-contract.md
│     └─ review-epic.md
│
├─ scripts/
│  ├─ gen_contracts.py
│  ├─ sync_generated_bundle.py
│  ├─ run_fixture_pipeline.py
│  ├─ build_reader.mjs
│  ├─ index_search.mjs
│  └─ release_bundle.py
│
├─ tests/
│  ├─ fixtures/
│  │  ├─ pdf/
│  │  ├─ extracted/
│  │  ├─ normalized/
│  │  ├─ localized/
│  │  └─ site-bundles/
│  ├─ backend/
│  ├─ frontend/
│  ├─ e2e/
│  └─ visual/
│
├─ docs/
│  ├─ adr/
│  ├─ specs/
│  ├─ architecture/
│  └─ operator-guides/
│
├─ artifacts/
│  ├─ .gitignore
│  ├─ cache/
│  ├─ runs/
│  ├─ releases/
│  └─ state/
│
└─ sources/
   └─ .gitignore
8. Contract-first package

Everything marked 🔒 must not be informal.

Contract	Purpose	Owner module	Consumers	Format	Change sensitivity	Test requirements
🔒 DocumentConfig	document declaration	models/config_models.py	config loader, run resolver	YAML -> Pydantic	High	schema validation, sample config tests
🔒 ModelProfile	model/provider/prompt config	models/config_models.py	translation planner, LLM gateway	YAML -> Pydantic	High	schema tests, profile resolution tests
🔒 RuleProfile	thresholds and QA behavior	models/config_models.py	normalize, QA, fix stage	YAML -> Pydantic	High	rule profile tests
🔒 SymbolPack	canonical symbol registry	models/config_models.py	asset resolver, exporter, frontend	YAML -> Pydantic	High	pack schema tests, symbol lookup tests
🔒 GlossaryPack	canonical terminology	models/config_models.py	planner, localizer, exporter, frontend glossary	YAML -> Pydantic	High	pack schema tests, glossary policy tests
🔒 PatchSet	deterministic overrides	models/config_models.py	normalize, asset resolver, fix stage	YAML -> Pydantic	High	patch schema tests, patch application tests
🔒 PipelineConfig	runtime execution policy	models/run_models.py	CLI, runner	JSON/Pydantic	Medium	CLI parse tests, config validation
🔒 ResolvedRunPlan	resolved doc + profile plan	models/run_models.py	runner, stages	JSON	High	resolution tests
🔒 RunManifest	run-level metadata	models/run_models.py	runner, inspect, CI, release	JSON	High	round-trip + manifest update tests
🔒 StageManifest	stage-level status and work unit tracking	models/run_models.py	runner, stages, resume logic	JSON	High	resume tests, status transition tests
🔒 DocumentManifest	immutable source PDF facts	models/manifest_models.py	extraction, enrich, export	JSON	High	ingest golden tests
🔒 ExtractedPage	raw page primitives + source refs	models/extract_models.py	normalize stage	JSON	Very high	schema tests, extraction goldens
🔒 PageRecord	canonical semantic page IR	models/ir_models.py	translation, localize, QA, export	JSON	Very high	schema tests, normalization goldens
🔒 Asset	resolved binary/logical asset	models/ir_models.py or asset_models.py	exporter, frontend	JSON	High	asset resolution tests
🔒 TranslationUnit	bounded LLM input contract	models/translation_models.py	planner, translate stage	JSON	Very high	planner tests, schema snapshot
🔒 TranslationResult	validated unit output	models/translation_models.py	translate stage, localize	JSON	Very high	validator tests, bad-response tests
🔒 QAIssue	machine-readable QA result	models/qa_models.py	QA engine, reports, release gate	JSONL	Very high	fingerprint tests, delta tests
🔒 NavigationTree	localized nav graph	models/site_bundle_models.py	export, frontend TOC	JSON	High	navigation tests, anchor tests
🔒 SearchDocument	internal search unit	models/site_bundle_models.py or build_models.py	enrich, QA, search smoke	JSONL	High	search-doc generation tests
🔒 SiteBundleManifest	public bundle root manifest	models/site_bundle_models.py	exporter, reader loaders	JSON	Very high	schema tests, export tests
🔒 BundlePage	reader-facing page payload	models/site_bundle_models.py	reader page route	JSON	Very high	schema tests, renderer tests
🔒 CatalogManifest	multi-doc reader entrypoint	models/site_bundle_models.py	catalog route	JSON	High	catalog loader tests
🔒 BuildArtifact	export/build asset inventory	models/site_bundle_models.py	export, package release	JSON	Medium	export manifest tests
🔒 ReleaseManifest	packaged release metadata	models/release_models.py	package/deploy, operator docs	JSON	High	release tests
Must-not-be-informal list

At minimum, these must exist before substantial implementation starts:

DocumentConfig

ModelProfile

RuleProfile

SymbolPack

GlossaryPack

PatchSet

ResolvedRunPlan

RunManifest

StageManifest

DocumentManifest

ExtractedPage

PageRecord

TranslationUnit

TranslationResult

QAIssue

SiteBundleManifest

BundlePage
9. Stage-by-stage implementation specs
9.1 resolve_run

Exact responsibility: resolve selected docs and all referenced profiles/packs into one immutable run plan.

Inputs: CLI args -> PipelineConfig, configs/catalog.yaml, referenced document/profile/pack YAMLs

Outputs: run_manifest.json, 00_resolve/resolved_run_plan.json, 00_resolve/resolved_configs.json

Deterministic logic: config loading, validation, hashing, stage plan creation

LLM-dependent logic: none

Persistence behavior: writes run root and seed manifests

Caching behavior: none

Retry behavior: none; fail fast on invalid config

Validation: all referenced profiles must exist; hashes must be recorded

Observability: run start log, selected docs, selected stages

Failure handling: stage fails with explicit config path + validation error

Tests required: config resolution test, duplicate doc test, missing profile test

9.2 ingest_source

Exact responsibility: read source PDF metadata and create immutable DocumentManifest

Inputs: ResolvedRunPlan, source PDF path

Outputs: 01_ingest/document_manifest.json, optional source snapshot metadata

Deterministic logic: hash file, read page count, sizes, metadata, outline/bookmarks

LLM-dependent logic: none

Persistence behavior: one document-level artifact

Caching behavior: cache by source_pdf_sha256 + stage_version

Retry behavior: document-level retry only

Validation: page count > 0; source file exists; hash consistent

Observability: source filename, page count, file bytes, ingest duration

Failure handling: fail stage; no partial success semantics needed

Tests required: valid PDF ingest, missing file, corrupted file

9.3 extract_primitives

Exact responsibility: extract per-page raw text/image/vector primitives and raw asset refs

Inputs: DocumentManifest, source PDF

Outputs: 02_extract/pages/pNNNN.json, 02_extract/assets/raw/**, 02_extract/manifest.json

Deterministic logic: PyMuPDF extraction of blocks/lines/spans, bbox, fonts, raw image refs

LLM-dependent logic: none

Persistence behavior: page-sharded JSON + raw asset files

Caching behavior: page-level cache by pdf_hash + page_no + stage_version

Retry behavior: retry failed pages individually; completed pages skipped on resume

Validation: extracted page matches schema; source refs present; page number consistent

Observability: pages/sec, spans/page, images/page, extraction errors by page

Failure handling: per-page failures recorded in stage manifest; strict mode may fail stage if any page fails

Tests required: page extraction, raw asset extraction, extraction goldens

9.4 normalize_layout

Exact responsibility: convert ExtractedPage into source-side semantic PageRecord

Inputs: extracted page JSON, RuleProfile, optional PatchSet

Outputs: 03_normalize/pages/pNNNN.json, 03_normalize/manifest.json

Deterministic logic: reading order, block segmentation, heading/list/callout/table/caption classification, stable IDs

LLM-dependent logic: none

Persistence behavior: one canonical IR page per source page

Caching behavior: page-level cache by extracted_page_hash + rule_profile_hash + patch_hash + stage_version

Retry behavior: per-page rerun

Validation: block tree valid, IDs unique, required anchors/fingerprints present

Observability: block counts by kind, fallback candidates, normalization duration/page

Failure handling: ambiguous pages may degrade to render_mode="hybrid" instead of hard-fail

Tests required: normalization unit tests, block tree goldens, hybrid fallback tests

9.5 resolve_assets_symbols

Exact responsibility: convert raw assets into resolved Asset records and attach canonical symbols

Inputs: normalized pages, extracted assets, SymbolPack

Outputs: 04_assets/pages/pNNNN.json, 04_assets/assets/*.json, derivative assets

Deterministic logic: symbol matching, figure-caption linking, asset classification, derivative generation

LLM-dependent logic: none

Persistence behavior: page records updated with asset/symbol refs; asset metadata persisted separately

Caching behavior: page-level by normalized_page_hash + symbol_pack_hash + stage_version

Retry behavior: per-page rerun

Validation: no duplicate symbol matches; missing assets become issues or unresolved refs, not silent drops

Observability: resolved symbol count, unresolved asset count, derivative generation timing

Failure handling: unresolved symbols are recorded and may become QA blockers later

Tests required: symbol resolution tests, asset pairing tests, derivative generation tests

9.6 plan_translation

Exact responsibility: collect translatable text nodes into bounded TranslationUnits

Inputs: 04_assets/pages/**, glossary pack, model profile, target locale

Outputs: 05_translation_plan/units/*.json, 05_translation_plan/index.json

Deterministic logic: select text-bearing inlines, freeze locked terms, group into units with context

LLM-dependent logic: none

Persistence behavior: unit-sharded JSON + plan index

Caching behavior: page-level planner cache by page_hash + glossary_hash + locale + stage_version

Retry behavior: per-page or per-unit plan regeneration

Validation: every translatable inline accounted for exactly once

Observability: units/page, chars/unit, TM hit candidates

Failure handling: conflicting glossary locks or oversize units fail the page plan

Tests required: planner coverage tests, unit size tests, locked-term tests

9.7 translate_units

Exact responsibility: obtain validated TranslationResult for each TranslationUnit

Inputs: unit JSON, model profile, prompt bundle, cache policy

Outputs: 06_translate/results/*.json, 06_translate/calls/*.json, 06_translate/failures/*.json

Deterministic logic: request shaping, cache keying, validation, retry sequencing

LLM-dependent logic: actual model call

Persistence behavior: one result file per accepted unit, one call metadata file per attempt

Caching behavior: shared cache by unit_hash + prompt_hash + model_profile_hash + locale + stage_version

Retry behavior: same request retry, smaller split retry, fallback model retry

Validation: strict Pydantic parse; exact ID set; placeholder integrity; glossary lock compliance

Observability: tokens, latency, cost estimate, invalid-output rate, fallback rate

Failure handling: failed units recorded individually; stage may continue in non-release mode

Tests required: mocked provider tests, cache hit tests, retry path tests, validation rejection tests
9.8 merge_localization

Exact responsibility: merge accepted translations into localized PageRecords

Inputs: 04_assets/pages/**, 06_translate/results/**, glossary pack

Outputs: 07_localize/pages/pNNNN.json

Deterministic logic: merge by exact inline ID, restore placeholders, add localized text per locale

LLM-dependent logic: none

Persistence behavior: page-sharded localized IR

Caching behavior: page-level cache by page_hash + relevant_result_hashes + glossary_hash + locale + stage_version

Retry behavior: per-page rerun

Validation: all required translatable inlines localized; no ID mismatches; no corrupted placeholders

Observability: translation coverage %, leakage count, glossary hit count

Failure handling: page fails if required results missing or inconsistent

Tests required: merge tests, English leakage tests, missing-unit tests

9.9 enrich_content

Exact responsibility: derive navigation, glossary index, search docs, and doc summary metadata

Inputs: localized pages, DocumentManifest, DocumentConfig

Outputs: 08_enrich/navigation.json, 08_enrich/search_documents.jsonl, 08_enrich/glossary_index.json, 08_enrich/doc_summary.json

Deterministic logic: heading tree generation, anchor generation, search text derivation, doc summary assembly

LLM-dependent logic: none

Persistence behavior: document-level JSON/JSONL

Caching behavior: doc-level by localized_page_hashes + stage_version

Retry behavior: document-level rerun

Validation: unique anchors, non-empty nav for valid docs, search doc URL validity

Observability: nav node count, search doc count, duplicate anchor count

Failure handling: duplicate anchors or invalid URLs fail the stage

Tests required: navigation tests, search doc generation tests, doc summary tests

9.10 evaluate_qa

Exact responsibility: run rule engine over localized/export-ready artifacts and compute acceptance

Inputs: localized pages, enrichment artifacts, rule profile, optional baseline ref

Outputs: 09_qa/issues.jsonl, 09_qa/summary.json, 09_qa/delta.json

Deterministic logic: pure rule execution, severity aggregation, delta comparison

LLM-dependent logic: none

Persistence behavior: canonical QA JSON/JSONL

Caching behavior: doc-level by input_hashes + rule_profile_hash + baseline_hash + stage_version

Retry behavior: document-level rerun

Validation: issue schema validity, deterministic fingerprinting, acceptance summary coherence

Observability: issues by severity/rule, new/resolved issue counts

Failure handling: rule exceptions fail the stage and identify offending rule

Tests required: rule tests, summary tests, delta tests

9.11 apply_safe_fixes

Exact responsibility: copy-forward pages and optionally apply deterministic safe fixes or emit patch suggestions

Inputs: localized pages, QA issues, patch set

Outputs: 10_fix/pages/*.json, 10_fix/suggestions.jsonl, 10_fix/validation.json

Deterministic logic: pass-through copy, enabled fix application, touched-page validation

LLM-dependent logic: none in default pipeline

Persistence behavior: always writes final-pre-export pages

Caching behavior: page-level by page_hash + issue_fingerprints + patch_hash + stage_version

Retry behavior: page-level rerun

Validation: output page schema; if fixes applied, touched pages must not introduce new blockers

Observability: pages copied, fixes applied, suggestions emitted

Failure handling: validation failure on fixed page fails the stage; pass-through mode should never alter content

Tests required: pass-through tests, safe-fix tests, validation regression tests

9.12 export_site_bundle

Exact responsibility: convert final internal artifacts into the public reader bundle

Inputs: fixed pages, assets, navigation, glossary index, doc summary

Outputs: 11_export/site_bundle/<doc_id>/**, 11_export/build_artifacts.json

Deterministic logic: public shape transformation, asset copying, path assignment, bundle manifest creation

LLM-dependent logic: none

Persistence behavior: document-scoped public bundle files

Caching behavior: doc-level by final_page_hashes + asset_hashes + stage_version

Retry behavior: document-level rerun

Validation: bundle manifest and bundle page schemas; all referenced assets exist

Observability: bundle size, file count, asset count

Failure handling: missing asset or invalid path fails export

Tests required: export contract tests, bundle snapshot tests, asset existence tests

9.13 build_reader

Exact responsibility: build static reader HTML from synced bundle(s)

Inputs: apps/reader/generated/**, reader app source

Outputs: 12_site/out/**

Deterministic logic: route generation, static rendering, HTML/CSS/JS build

LLM-dependent logic: none

Persistence behavior: static site output

Caching behavior: delegate to Next build cache; pipeline records output hash and build metadata

Retry behavior: rerun whole site build

Validation: all doc/page routes generated, no missing generated bundle files

Observability: build duration, route count, bundle size stats

Failure handling: any build failure fails the stage with captured logs

Tests required: build smoke test, route coverage test

9.14 index_search

Exact responsibility: build Pagefind index from static HTML and verify a smoke query

Inputs: 12_site/out/**

Outputs: 13_search/pagefind/**, smoke test log

Deterministic logic: run Pagefind, verify index files and metadata

LLM-dependent logic: none

Persistence behavior: search index files under site output or staged output

Caching behavior: by built HTML hash + stage version

Retry behavior: rerun whole stage

Validation: index directory exists; smoke query returns expected fixture result

Observability: index size, index build duration, smoke query result count

Failure handling: missing/invalid index fails stage

Tests required: Pagefind smoke test, fixture query test

9.15 package_release

Exact responsibility: enforce release gate and package deployable site with release metadata

Inputs: accepted QA summary, static site output, search index, deployment config

Outputs: 14_release/release_manifest.json, packaged release dir/archive

Deterministic logic: release gating, manifest assembly, package layout

LLM-dependent logic: none

Persistence behavior: packaged release under run + optional artifacts/releases/<release_id>/

Caching behavior: none

Retry behavior: rerun if packaging or deploy fails

Validation: accepted run present; release manifest complete

Observability: package bytes, included docs, release ID, deploy target

Failure handling: rejection or deploy failure clearly recorded; no silent publish

Tests required: release gate tests, manifest tests, mocked deploy tests

10. Frontend implementation specs
10.1 Route/data loader module

Responsibility: load CatalogManifest, SiteBundleManifest, BundlePage, glossary and nav artifacts from apps/reader/generated

Props/data contract: typed filesystem loaders returning contract-validated objects

Dependencies: @aeon-reader/contracts, Next server environment, generated bundle path helpers

Failure modes: missing file, invalid JSON, unknown doc/page

Tests: loader unit tests, not-found tests

Performance considerations: cache file reads within request/build process; no client fetches for main content

Accessibility considerations: not direct UI, but must support route-level not-found handling
10.2 App shell

Responsibility: global layout, header, theme, container layout

Props/data contract: children, optional doc context, theme state

Dependencies: ThemeProvider, route helpers

Failure modes: shell render failure should be isolated by top error boundary

Tests: shell rendering, theme toggle, layout snapshot

Performance considerations: client boundary limited to theme and small UI state

Accessibility considerations: skip link, semantic landmarks, focus-visible styles

10.3 Document layout

Responsibility: compose sidebar, content column, glossary drawer slot, page nav

Props/data contract: docSummary, navigation, active page metadata, page content

Dependencies: loaders, sidebar, TOC, page nav

Failure modes: missing nav node, bad page number

Tests: integration render with fixture doc

Performance considerations: sidebar collapse state client-only; main content stays server-rendered

Accessibility considerations: logical heading order, keyboard-accessible sidebar toggle

10.4 Catalog route

Responsibility: render multi-document landing page

Props/data contract: CatalogManifest

Dependencies: bundle loader

Failure modes: empty catalog, invalid doc summary

Tests: route render test, static build test

Performance considerations: static route, no client JS needed

Accessibility considerations: semantic list/card structure

10.5 Document landing route

Responsibility: render per-document overview, stats, entry links

Props/data contract: doc summary, nav preview, glossary preview

Dependencies: bundle loader

Failure modes: missing summary bundle

Tests: route render test

Performance considerations: static route

Accessibility considerations: clear landmarks and descriptive links

10.6 Reader page route

Responsibility: render one BundlePage and surrounding navigation controls

Props/data contract: BundlePage, doc nav, page nav data

Dependencies: PageView, DocLayout

Failure modes: invalid block kind, missing asset reference, unknown anchor

Tests: fixture page render tests, route coverage tests

Performance considerations: page content server-rendered; only interactive leaves hydrate

Accessibility considerations: semantic headings/lists/tables/figures, correct anchor link targets

10.7 PageView

Responsibility: map a BundlePage to DOM sections and stable anchor IDs

Props/data contract: page: BundlePage

Dependencies: BlockRenderer

Failure modes: duplicate block IDs, invalid anchor IDs

Tests: page render snapshot, anchor link tests

Performance considerations: pure render, memoizable helpers only

Accessibility considerations: section labels and heading hierarchy

10.8 BlockRenderer

Responsibility: exhaustive dispatch over block.kind

Props/data contract: block, assetsById, locale, optional doc context

Dependencies: block-specific components, assertNever

Failure modes: unsupported block kind

Tests: one test per block kind + assert-never coverage

Performance considerations: no regex or parsing work at render time

Accessibility considerations: use native elements where possible

10.9 InlineRenderer

Responsibility: exhaustive dispatch over inline.kind

Props/data contract: inline union, symbol map, glossary map, xref resolver

Dependencies: SymbolInline, GlossaryLink, route helpers

Failure modes: unsupported inline kind, broken xref target

Tests: text, symbol, xref, glossary-hit rendering tests

Performance considerations: no runtime glossary matching

Accessibility considerations: symbol alt labels, keyboard/focus support for glossary/xref interactions

10.10 Sidebar / TOC

Responsibility: render doc navigation tree and active page/section state

Props/data contract: NavigationTree, activePage, optional activeAnchor

Dependencies: route helpers

Failure modes: invalid tree shape, cycles should have been impossible upstream

Tests: tree render, active state, keyboard navigation

Performance considerations: static tree, client only for collapse state if needed

Accessibility considerations: nav landmark, aria-expanded, keyboard traversal

10.11 Page navigation

Responsibility: previous/next page controls and page label

Props/data contract: prevPage, nextPage, current page metadata

Dependencies: route helpers

Failure modes: missing neighbor pages at boundaries

Tests: boundary and middle-page navigation tests

Performance considerations: Next Link prefetch for neighbor routes

Accessibility considerations: descriptive labels, disabled states

10.12 Search dialog

Responsibility: lazy-load Pagefind, run doc-scoped searches, render results

Props/data contract: current docId, open/close state

Dependencies: lib/pagefind.ts, route helpers

Failure modes: index missing, Pagefind load failure, empty results

Tests: mocked search tests, e2e search flow

Performance considerations: no Pagefind import until first open; cache loaded instance

Accessibility considerations: focus trap, ESC close, keyboard result navigation

10.13 Glossary drawer and glossary page

Responsibility: show term definitions from precomputed glossary index

Props/data contract: glossary entries, active term ID

Dependencies: glossary bundle

Failure modes: missing term ID, inconsistent glossary hit

Tests: drawer open/close, glossary page render, keyboard tests

Performance considerations: lightweight client state only

Accessibility considerations: dialog semantics, focus restore, linkable glossary route

10.14 Symbol rendering module

Responsibility: render canonical symbol visuals and labels by symbol_id

Props/data contract: symbolId, label data, display mode

Dependencies: exported symbol asset map or inline SVG component map

Failure modes: missing symbol asset/component

Tests: known symbol render tests, missing symbol fallback tests

Performance considerations: sprite/component map loaded with page bundle, not by network lookup

Accessibility considerations: decorative vs semantic symbol labeling

10.15 Figure/lightbox module

Responsibility: render block-level figures and optional enlarged view

Props/data contract: asset, optional caption, open state

Dependencies: bundle asset map

Failure modes: missing derivative, broken image path

Tests: figure render, lightbox open/close, missing asset fallback

Performance considerations: lightbox client-only, image sizes from exported derivatives

Accessibility considerations: alt text, dialog semantics, keyboard close

10.16 Theme provider

Responsibility: user theme preference and CSS variable mode switch

Props/data contract: children

Dependencies: theme.css

Failure modes: storage access edge cases

Tests: theme toggle, persistence tests

Performance considerations: tiny client boundary

Accessibility considerations: contrast in both modes, reduced motion support

10.17 Error boundaries and not-found handling

Responsibility: isolate failures in route/content/search/lightbox boundaries

Props/data contract: child tree and fallback UI

Dependencies: Next error.tsx, boundary components

Failure modes: runtime exceptions in interactive components

Tests: injected-failure tests, route not-found tests

Performance considerations: boundaries should be coarse enough to be useful, not everywhere

Accessibility considerations: readable fallback messages and recovery links
10.18 Caching/prefetch utilities

Responsibility: route prefetch and in-process bundle loader caching

Props/data contract: doc/page route helpers

Dependencies: Next routing and server module cache

Failure modes: stale route helper logic, over-prefetching

Tests: helper tests, navigation smoke

Performance considerations: only prefetch adjacent pages and likely sidebar targets

Accessibility considerations: prefetching must not interfere with focus or announce noisy loading states

11. Data/artifact lifecycle map
Artifact / path	Written by	Read by	Canonical or derived	Versioned	Cacheable	Git status
packages/contracts/jsonschema/*.json	contract generation script	TS generation, tests	Derived from Pydantic, canonical for interop	Yes	No	Checked in
packages/contracts/typescript/src/generated/*.ts	TS generation script	reader app	Derived	Yes	No	Checked in
artifacts/state/accepted_runs.json	runner/release tooling	QA, release, operator tools	Canonical state pointer	Yes	No	Ignored
artifacts/state/baselines.json	QA/release tooling	QA delta	Canonical state pointer	Yes	No	Ignored
artifacts/runs/<run>/<doc>/run_manifest.json	resolve_run / runner	all stages, inspect tools	Canonical run metadata	Yes	No	Ignored
00_resolve/resolved_run_plan.json	resolve_run	runner, stages	Canonical	Yes	No	Ignored
01_ingest/document_manifest.json	ingest_source	extract, enrich, export	Canonical	Yes	Yes	Ignored
02_extract/pages/*.json	extract_primitives	normalize	Canonical	Yes	Yes	Ignored
02_extract/assets/raw/**	extract_primitives	asset resolver	Canonical raw binary	Content-hash versioned	Yes	Ignored
03_normalize/pages/*.json	normalize_layout	asset resolver, planner	Canonical	Yes	Yes	Ignored
04_assets/pages/*.json	resolve_assets_symbols	planner, localize	Canonical	Yes	Yes	Ignored
04_assets/assets/*.json	resolve_assets_symbols	export, frontend via bundle	Canonical	Yes	Yes	Ignored
05_translation_plan/units/*.json	plan_translation	translate_units	Canonical	Yes	Yes	Ignored
06_translate/results/*.json	translate_units	merge_localization	Canonical	Yes	Yes	Ignored
06_translate/calls/*.json	translate_units	audit/bench tools	Derived audit log	Yes	No	Ignored
07_localize/pages/*.json	merge_localization	enrich, QA, fixes	Canonical	Yes	Yes	Ignored
08_enrich/navigation.json	enrich_content	QA, export, reader	Canonical derived doc artifact	Yes	Yes	Ignored
08_enrich/search_documents.jsonl	enrich_content	QA, search smoke, analytics	Canonical derived doc artifact	Yes	Yes	Ignored
08_enrich/glossary_index.json	enrich_content	export, reader	Canonical derived doc artifact	Yes	Yes	Ignored
09_qa/issues.jsonl	evaluate_qa	reports, release gate	Canonical QA source	Yes	Yes	Ignored
09_qa/summary.json	evaluate_qa	release gate, operator tools	Canonical QA summary	Yes	Yes	Ignored
09_qa/delta.json	evaluate_qa	operator tools, reports	Canonical delta	Yes	Yes	Ignored
09_qa/report.md / .html	report generator	humans	Derived	Yes	No	Ignored
10_fix/pages/*.json	apply_safe_fixes	export	Canonical final-pre-export pages	Yes	Yes	Ignored
10_fix/suggestions.jsonl	apply_safe_fixes	humans, later tooling	Canonical suggestion output	Yes	Yes	Ignored
11_export/site_bundle/<doc_id>/**	export_site_bundle	sync script, reader	Canonical public bundle	Yes	Yes	Ignored
11_export/build_artifacts.json	export_site_bundle	build/release tooling	Canonical export inventory	Yes	Yes	Ignored
apps/reader/generated/**	sync script	reader build/tests	Derived local build input	No run history	No	Ignored
12_site/out/**	build_reader	Pagefind, package release	Derived	Yes by run	No	Ignored
13_search/pagefind/**	index_search	deployed site	Derived	Yes by run	No	Ignored
14_release/release_manifest.json	package_release	deploy/operator tooling	Canonical release metadata	Yes	No	Ignored
artifacts/releases/<release_id>/**	package_release	deploy rollback/audit	Canonical packaged release	Yes	No	Ignored
12. CI gates
12.1 Minimal v1 CI

Run on every PR.

Checks

install Python and Node deps

make lint

make typecheck

make schemas

fail if generated contracts changed after regeneration

backend smoke/unit tests

reader static build against fixture bundle

Blocking conditions

lint failure

typecheck failure

schema generation drift

backend test failure

reader build failure

12.2 Recommended CI

Enable once export bundle and reader routes exist.

Checks

all minimal checks

fixture pipeline through export_site_bundle

backend integration tests

backend golden artifact tests

frontend unit/component tests

Playwright e2e on fixture site

protected visual snapshot tests

QA acceptance on fixture run

Blocking conditions

any backend integration or golden failure

any frontend unit/component failure

any Playwright e2e failure

any protected visual snapshot failure

fixture QA summary contains blocker issues

12.3 Later CI

Enable once real-doc runs and release packaging exist.

Checks

all recommended checks

nightly real-doc build on selected documents

non-blocking live LLM structured-output smoke tests on tiny corpus

benchmark comparison for translation profiles

package release dry run

preview deploy on PR

gated production deploy on manual/tagged release

Blocking conditions

for PRs: same as recommended CI

for release workflow:

accepted run pointer missing

release manifest generation failure

package/deploy failure

full-doc QA blocker issues

12.4 Exact blocking rules to hard-code

generated schemas or TS types differ from committed output

any canonical artifact written in tests fails schema validation

any fixture run produces error severity QAIssue

any static reader route fails to build

any e2e search/navigation test fails

any route-level visual baseline diff exceeds threshold

any workflow step uses unpublished contract changes not regenerated into packages/contracts

13. Agent execution plan
13.1 Work packet model

Use packets that are:

small enough for one focused agent branch

large enough to produce a meaningful merged increment

aligned to directory boundaries

13.2 Agent context every packet must receive

Each agent should receive:

this implementation spec

the relevant epic/task subset only

current repo tree

locked assumptions section

protected files/areas list

exact validation command

definition of done

13.3 Forbidden to change without explicit approval

stage order

artifact path layout

selected tech stack

public bundle boundary

contract generation direction

route scheme

whether markdown is canonical

LLM scope boundary

single sources of truth under configs/

13.4 Outputs every agent must produce

Every packet must end with:

code changes

tests

updated generated contracts if relevant

brief implementation note:

files changed

commands run

known limitations

follow-up tasks

13.5 How to reduce merge conflicts
assign single-writer ownership for models/* in any one packet

do not let multiple packets edit the same contract file simultaneously

keep frontend packets out of backend model files unless contract regeneration is explicitly in scope

regenerate packages/contracts only in packets that intentionally change Pydantic models

merge contract packets before downstream consumers branch

13.6 Recommended packets
PKT-01 — Workspace bootstrap

Scope boundary: root files, package scaffolds, local commands

Expected size: S

Prerequisites: none

Files touched: root files, package scaffolds

Validation command: make bootstrap && make lint

Merge criteria: fresh clone bootstraps and both packages install

PKT-02 — Core contracts and config models

Scope boundary: Pydantic model base set + config schemas + contract generation

Expected size: M

Prerequisites: PKT-01

Files touched: models/*, configs/*, contract generation scripts, packages/contracts/**

Validation command: make schemas && make typecheck && pytest tests/backend/test_config_loader.py

Merge criteria: generated contracts stable and checked in

PKT-03 — Artifact runtime and stage runner

Scope boundary: artifact IO, manifests, cache keys, runner, CLI

Expected size: M

Prerequisites: PKT-02

Files touched: io/*, cache/*, stage_framework/*, cli/main.py

Validation command: pytest tests/backend/test_runner.py tests/backend/test_artifact_store.py

Merge criteria: stub stages run/resume through CLI

PKT-04 — Ingest and primitive extraction

Scope boundary: ingest_source, extract_primitives, extraction contracts, extraction tests

Expected size: M

Prerequisites: PKT-03

Files touched: stages/ingest_source.py, stages/extract_primitives.py, models/extract_models.py, fixture tests

Validation command: pytest tests/backend/test_ingest_source.py tests/backend/test_extract_*

Merge criteria: fixture PDFs ingest and extract deterministically

PKT-05 — IR normalization and asset/symbol resolution

Scope boundary: IR models, normalization, asset resolver, patches, fallback policy

Expected size: L

Prerequisites: PKT-04

Files touched: models/ir_models.py, stages/normalize_layout.py, stages/resolve_assets_symbols.py, config/*loader.py

Validation command: pytest tests/backend/test_normalize_layout.py tests/backend/test_symbol_resolution.py

Merge criteria: normalized fixture pages match expected block trees

PKT-06 — Translation subsystem

Scope boundary: planner, placeholders, LLM gateway, validator, translate stage

Expected size: L

Prerequisites: PKT-05

Files touched: models/translation_models.py, llm/*, stages/plan_translation.py, stages/translate_units.py

Validation command: pytest tests/backend/test_translation_* tests/backend/test_llm_validation.py

Merge criteria: mocked translation flow validates and resumes correctly

PKT-07 — Localization, enrichment, and QA

Scope boundary: merge localization, navigation/search docs, QA engine, reports, fix stage

Expected size: L

Prerequisites: PKT-06

Files touched: stages/merge_localization.py, stages/enrich_content.py, qa/*, stages/evaluate_qa.py, stages/apply_safe_fixes.py

Validation command: pytest tests/backend/test_merge_localization.py tests/backend/test_qa_*

Merge criteria: fixture localized bundle and QA summary are deterministic

PKT-08 — Public bundle export and build wrappers

Scope boundary: public bundle models/exporter, sync script, build/index/package wrappers

Expected size: M

Prerequisites: PKT-07

Files touched: models/site_bundle_models.py, stages/export_site_bundle.py, stages/build_reader.py, stages/index_search.py, scripts

Validation command: pytest tests/backend/test_export_site_bundle.py && make fixture-site-build

Merge criteria: reader can build from synced exported fixture bundle

PKT-09 — Reader core
Scope boundary: route loaders, shell, doc layout, page renderer, catalog/glossary routes

Expected size: L

Prerequisites: PKT-08

Files touched: apps/reader/app/**, components/**, lib/**

Validation command: pnpm --filter reader test && pnpm --filter reader build

Merge criteria: static reader renders fixture bundle end-to-end

PKT-10 — Search, hardening, and CI

Scope boundary: search dialog, TOC/nav, lightbox, boundaries, e2e/visual, GitHub Actions, deploy docs, second-doc proof

Expected size: L

Prerequisites: PKT-09

Files touched: reader interactive modules, tests, workflow files, docs, second doc config

Validation command: pnpm --filter reader test:e2e && make ci-local

Merge criteria: full recommended CI passes and second doc builds without code changes

14. Spec-kit decomposition
14.1 Epics list

EP-001 Workspace, toolchain, and contract foundation

EP-002 Config system, artifact runtime, and stage framework

EP-003 Source ingest and primitive extraction

EP-004 Canonical IR normalization and asset/symbol resolution

EP-005 Translation planning and execution

EP-006 Localization merge, navigation, glossary, and search docs

EP-007 QA, safe fixes, reports, and baselines

EP-008 Site bundle export and build/deploy bridge

EP-009 Reader frontend core

EP-010 Search, accessibility, performance, and resilience

EP-011 Test harness, CI/CD, deployment, and multi-document hardening

14.2 Per-epic task list

EP-001: T001-01..T001-04

EP-002: T002-01..T002-04

EP-003: T003-01..T003-04

EP-004: T004-01..T004-04

EP-005: T005-01..T005-04

EP-006: T006-01..T006-04

EP-007: T007-01..T007-04

EP-008: T008-01..T008-04

EP-009: T009-01..T009-04

EP-010: T010-01..T010-04

EP-011: T011-01..T011-04

14.3 Acceptance criteria structure

Each spec doc should contain:

objective

boundaries

required inputs

deliverables

validation command

definition of done

files expected to change

prohibited changes

follow-up hooks

14.4 Dependencies graph
EP-001
  -> EP-002
    -> EP-003
      -> EP-004
        -> EP-005
          -> EP-006
            -> EP-007
              -> EP-008
                -> EP-009
                  -> EP-010
                    -> EP-011

Parallel branches:

EP-009 shell scaffolding can start after EP-001 + public bundle stub from EP-008 is defined

parts of EP-011 can start incrementally after each earlier epic lands

14.5 Suggested spec document names
docs/specs/ep-001-workspace-foundation.md
docs/specs/ep-002-config-runtime-runner.md
docs/specs/ep-003-ingest-extract.md
docs/specs/ep-004-ir-normalize-assets.md
docs/specs/ep-005-translation.md
docs/specs/ep-006-localize-enrich.md
docs/specs/ep-007-qa-fixes.md
docs/specs/ep-008-export-build-release.md
docs/specs/ep-009-reader-core.md
docs/specs/ep-010-reader-hardening.md
docs/specs/ep-011-testing-ci-multidoc.md
14.6 Suggested ADR names
docs/adr/0001-canonical-ir-no-markdown.md
docs/adr/0002-generated-contracts-from-pydantic.md
docs/adr/0003-immutable-filesystem-artifacts.md
docs/adr/0004-custom-stage-runner.md
docs/adr/0005-llm-translation-boundary.md
docs/adr/0006-public-site-bundle-boundary.md
docs/adr/0007-hybrid-fallback-policy.md
docs/adr/0008-pagefind-static-search.md
docs/adr/0009-next-static-reader.md
docs/adr/0010-safe-fix-stage-policy.md
docs/adr/0011-config-packs-single-source.md
docs/adr/0012-baseline-qa-and-release-gating.md
docs/adr/0013-multi-document-routing.md
14.7 Suggested checklists

contract change checklist

new stage checklist

new frontend module checklist

new rule checklist

exported bundle change checklist

release readiness checklist

second-document onboarding checklist

14.8 Suggested prompt-pack file names
prompts/agents/implement-backend-stage.md
prompts/agents/implement-schema.md
prompts/agents/implement-frontend-module.md
prompts/agents/write-tests.md
prompts/agents/write-adr.md
prompts/agents/refactor-no-behavior-change.md
prompts/agents/validate-contract.md
prompts/agents/review-epic.md
15. Prompt pack for coding agents
15.1 Implementing a new backend stage
You are implementing backend stage: <stage_name>.

Read first:
- docs/specs/<epic-spec>.md
- docs/adr/0001-canonical-ir-no-markdown.md
- docs/adr/0002-generated-contracts-from-pydantic.md
- docs/adr/0003-immutable-filesystem-artifacts.md
- this task definition: <task_id>

Scope:
- Only implement <stage_name> and directly related helpers/tests.
- Do not change stage order, artifact paths, or public contracts unless the task explicitly requires it.

Inputs:
- Input contracts: <list>
- Output contracts: <list>
- Stage path: packages/pipeline/src/aeon_reader_pipeline/stages/<stage_name>.py

Required outputs:
- stage implementation
- stage tests
- manifest/status updates if needed
- any required model additions
- updated generated contracts only if models changed

Rules:
- Use typed Pydantic models for all persisted artifacts.
- Use ArtifactStore for all file IO.
- Record structured logs with run_id/doc_id/stage/work_unit.
- Make failure handling explicit and resume-safe.
- Do not put business thresholds in code; read them from RuleProfile.
- No raw dict JSON writes.

Validation:
- Run: <exact command>
- Ensure tests pass.
- Summarize files changed and any unresolved edge cases.

Return:
1. what you changed
2. files changed
3. commands run
4. follow-up work needed
15.2 Implementing a new schema/model
You are implementing or changing schema/model: <model_name>.

Read first:
- docs/adr/0002-generated-contracts-from-pydantic.md
- docs/specs/<relevant-epic>.md
- existing model files in packages/pipeline/src/aeon_reader_pipeline/models/

Scope:
- Define/modify the model and any direct validators/helpers.
- Update schema generation if needed.
- Update tests and generated contract outputs.

Required outputs:
- Pydantic model
- schema generation compatibility
- tests: round-trip, validation, example artifact
- regenerated JSON Schema and TypeScript types if the model is exported

Rules:
- Prefer discriminated unions over ad hoc dict payloads.
- Preserve backward compatibility unless the task explicitly allows a schema break.
- Document change sensitivity in comments if the model is high-risk.
- Do not hand-edit generated TS artifacts except through the generator.

Validation:
- Run: make schemas && make typecheck && pytest <relevant tests>

Return:
1. contract summary
2. compatibility impact
3. regenerated files
4. required downstream updates
15.3 Implementing a frontend module
You are implementing frontend module: <module_name>.

Read first:
- docs/specs/<frontend-epic>.md
- docs/adr/0006-public-site-bundle-boundary.md
- docs/adr/0009-next-static-reader.md
- contracts used by this module in packages/contracts/

Scope:
- Implement only the module and its tests.
- Do not add runtime content repair.
- Do not add new data fetching patterns outside the defined bundle loader path.

Inputs:
- Props/data contract: <contract names>
- Files to create/update: <list>

Rules:
- Use TypeScript types from @aeon-reader/contracts only.
- Use exhaustive rendering for union types.
- Keep client components as small leaves.
- No markdown parsing or dangerous HTML injection.

Validation:
- Run: pnpm --filter reader test -- <relevant test> && pnpm --filter reader build

Return:
1. module behavior
2. files changed
3. tests added
4. any follow-up UI debt
15.4 Writing tests for a module
You are writing tests for: <target_module_or_stage>.

Read first:
- task spec for the target
- relevant ADRs
- existing fixture patterns in tests/

Scope:
- Add or improve tests only.
- Do not refactor implementation unless absolutely required for testability, and keep such changes minimal.

Test requirements:
- cover happy path
- cover at least one invalid input / failure mode
- use typed fixtures
- avoid brittle snapshots unless explicitly requested

Validation:
- Run the narrowest relevant test command first, then the broader package command.

Return:
1. test coverage added
2. fixtures added or reused
3. commands run
4. known uncovered edge cases
15.5 Writing an ADR
You are writing ADR: <adr_id> <title>.

Read first:
- current architecture spec
- related epic spec
- existing ADR format in docs/adr/

Structure:
- Context
- Decision
- Consequences
- Alternatives considered
- Status

Rules:
- Record the decision that is already chosen.
- Do not redesign the architecture.
- Be explicit about what is locked and what remains flexible.

Validation:
- Ensure ADR matches actual repo and task boundaries.

Return:
1. ADR file path
2. decision summary
3. implications for implementation
15.6 Refactoring without changing behavior
You are refactoring: <module_or_stage> without changing behavior.

Read first:
- current tests
- current contracts
- relevant ADRs

Scope:
- improve structure/readability only
- no contract changes
- no path changes
- no stage ordering changes

Rules:
- preserve all artifact shapes
- preserve logging and error behavior
- add tests before refactor if protection is weak

Validation:
- run existing tests before and after
- no generated contract diffs allowed

Return:
1. what was refactored
2. proof behavior is unchanged
3. files changed
15.7 Validating an artifact contract
You are validating artifact contract: <artifact_name>.

Read first:
- model definition
- sample artifacts
- consumer modules

Tasks:
- confirm schema completeness
- confirm example artifact validity
- confirm consumer assumptions match schema
- identify hidden informal fields or undocumented behavior

Rules:
- do not change implementation unless asked
- report any ambiguous or unstable field
- flag fields that should be derived rather than stored

Validation:
- run schema validation tests
- run at least one consumer compile/test path

Return:
1. contract findings
2. required fixes
3. downstream risks
15.8 Reviewing a completed epic
You are reviewing completed epic: <epic_id>.

Read first:
- epic spec
- merged files for the epic
- test output
- ADRs referenced by the epic

Review checklist:
- scope respected
- contracts formalized
- no forbidden boundary violations
- tests present and meaningful
- validation commands reproducible
- generated files refreshed where required
- no duplicate sources of truth introduced

Output:
1. pass/fail by acceptance criterion
2. deviations from spec
3. risks before merge/release
4. exact remediation items
16. Initial milestones
Milestone 1 — English structural proof

Scope: EP-001, EP-002, EP-003, enough of EP-004 and EP-008/EP-009 to render one English fixture page

Why it is the right milestone: it proves repo structure, contracts, extraction, normalization, export, and reader rendering before translation exists

Demo outcome: open a static reader page generated from a fixture PDF and rendered from BundlePage

Files/artifacts expected:

DocumentManifest

ExtractedPage

PageRecord

minimal SiteBundleManifest

one BundlePage

working /docs/<doc>/page/1

Tests required:

config loader tests

artifact store tests

extraction tests

normalization tests

static reader build test

Exit criteria: fixture PDF flows from source to rendered static page with no runtime content repair

Milestone 2 — Russian localized fixture bundle with QA
Scope: EP-005, EP-006, EP-007, complete internal localized pipeline on fixture corpus

Why it is the right milestone: it proves the LLM boundary, localization merge, glossary annotation, nav/search derivation, and machine-readable QA

Demo outcome: one or more Russian fixture pages render correctly, QA summary exists, and no blocker issues remain on fixture set

Files/artifacts expected:

TranslationUnit

TranslationResult

localized PageRecord

NavigationTree

SearchDocument

QAIssue outputs

Tests required:

planner tests

placeholder/validator tests

merge localization tests

QA rule tests

localized bundle render tests

Exit criteria: localized fixture run is reproducible and QA-gated

Milestone 3 — Deployable static reader with search

Scope: EP-008, EP-009, EP-010, enough of EP-011 for preview deploy

Why it is the right milestone: it proves the end-to-end product shape and delivery path

Demo outcome: preview deployment with catalog, document route, page route, glossary, search dialog, theme, and stable e2e/visual checks

Files/artifacts expected:

11_export/site_bundle/**

apps/reader/generated/**

12_site/out/**

13_search/pagefind/**

CI workflows

Tests required:

export tests

reader component tests

Playwright e2e

visual snapshots

Exit criteria: CI builds and preview-deploys the static reader from fixture bundle and passes recommended gates

17. Anti-patterns and guardrails
17.1 Likely implementation mistakes agents will make

passing raw argparse or CLI values deep into stages

writing raw dicts to JSON instead of validated models

adding stage-local magic constants instead of RuleProfile

letting the frontend read raw run artifacts

storing duplicate derived fields as canonical data

implementing markdown parsing/rendering in the reader

using regex-based glossary linking in React

hardcoding doc_id, model names, or route bases in code

putting provider-specific logic directly inside stage code

silently mutating pages in the fix stage

introducing a database “just for convenience”

creating multiple symbol or glossary sources

17.2 Architectural boundaries that must not be violated

pipeline stages communicate via typed artifacts, not implicit globals

frontend consumes exported bundle only

contracts originate in Python models only

LLM integration is behind LlmGateway

config lives under configs/**

release gating reads QA JSON, not markdown reports

search is static and based on exported/built site artifacts

17.3 What must remain deterministic

artifact paths

stage ordering

ID and fingerprint generation

normalization and layout classification rules

glossary linking

symbol resolution

navigation generation

search document generation

export bundle layout

reader rendering from bundle data

QA issue generation from fixed inputs

17.4 What must never be pushed into the frontend runtime

markdown repair

structure reconstruction

glossary regex linking

symbol detection

translation fallback

QA heuristics

search-index construction

asset pairing logic

configuration resolution

17.5 What must never be schema-less

any persisted artifact under artifacts/runs/**

document configs and profiles

exported reader bundle files

translation unit/result payloads

QA issues and summaries

run manifests and stage manifests

release manifests

patch/override definitions

17.6 What must never be duplicated as multiple sources of truth

doc_id, titles, route base

model selection

rule thresholds

symbol definitions

glossary terms and variants

prompt bundle identity

active accepted run and baseline run pointers

public bundle file layout

search metadata fields

17.7 Guardrails for agents

no new dependencies without justification in task notes

no editing generated contracts by hand

no inline JSON schema fragments duplicated in multiple modules

no ad hoc shell scripts in place of stage or script modules

no side-effecting logic in rule functions

no broad refactors outside packet boundary

18. Final delivery checklist
18.1 Foundation is complete when

root workspace boots on a fresh clone

packages/pipeline, packages/contracts, and apps/reader all build/install

core config and artifact contracts exist as Pydantic models

JSON Schema and TS types generate and are checked in

ArtifactStore, RunManifest, StageManifest, runner, and CLI exist

sample configs validate

local lint, typecheck, and smoke tests pass

18.2 Pipeline is functional when

a fixture PDF ingests into DocumentManifest

extraction produces valid ExtractedPage artifacts

normalization produces valid PageRecord artifacts

asset/symbol resolution works on fixture pages

translation units are planned and translated through mocked/provider path

localization merge produces valid localized pages

enrichment produces nav/search/glossary artifacts

QA emits issues.jsonl and summary.json

export produces a valid public site bundle

18.3 Reader is functional when

catalog route builds statically

document landing route builds statically

page routes build statically from generated bundle

block and inline rendering cover all supported kinds

glossary page/drawer works from precomputed data

next/previous navigation works

theme toggle works

search works through Pagefind

route-level failures are caught by boundaries, not white-screened

18.4 QA is trustworthy when

QAIssue is canonical and fully typed

issue fingerprints are stable across identical runs

rule thresholds live only in RuleProfile

reports derive from JSON, not the reverse

baseline deltas correctly classify new/resolved/regressed issues

fixture QA runs are deterministic

release gating reads only machine-readable QA artifacts

18.5 System is ready for iterative document expansion when

a second document can be added via config and content only

multi-doc catalog renders both documents

no code changes are required to add another document with the same architecture

symbol/glossary packs can be reused or extended without drift

accepted-run and baseline pointers are per-document and stable

fixture and CI workflows support more than one document

operator docs describe add-a-document workflow clearly
