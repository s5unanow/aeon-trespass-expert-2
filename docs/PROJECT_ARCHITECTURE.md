1. Executive Summary

Build this as one repo with two bounded products:

a content compiler in Python that turns source PDFs into a versioned, validated, language-specific site bundle, and

a static reader application in Next.js that consumes that bundle and produces the deployable reader site.

The content compiler is the real product core. It ingests an English rules PDF, extracts low-level page primitives, normalizes them into a canonical block-preserving intermediate representation (IR), translates only text-bearing nodes into Russian through a tightly bounded LLM layer, runs deterministic QA, and exports a fully typed site bundle. The reader app is intentionally thin: it renders the already-correct bundle into static HTML, adds search, navigation, glossary UX, and theme/accessibility behavior, but it does not repair content at runtime.

The core architectural principles are:

Canonical IR first. No markdown-first pipeline. Markdown is optional debug/export output only.

Typed contracts at every stage. Every stage reads a specific versioned artifact and writes a specific versioned artifact.

Deterministic structure, bounded LLM semantics. Layout, blocks, navigation, assets, glossary linking, and rendering are deterministic. LLMs translate text only.

JSON-first QA. Machine-readable issues are the source of truth; markdown and HTML reports are derived views.

Immutable runs + resumable units. Every run is reproducible, cacheable, diffable, and restartable.

Single sources of truth. Document config, rules, glossary, symbol specs, and model profiles each live in one canonical location.

Static delivery. The deployed reader is static output, not a server-heavy application.

This is superior to a naive extract -> translate -> repair markdown -> render flow because it never asks a model to preserve or reconstruct structure it did not own in the first place. Structure is captured deterministically from PDF primitives, represented explicitly in the IR, and rendered by code. Translation happens against stable block/inline IDs, so headings remain headings, lists remain lists, symbols remain symbols, and QA can point to exact blocks instead of guessing after-the-fact from broken strings.

2. Recommended Technology Stack
Backend language/runtime

Python 3.12

Use Python for the content compiler. It has the strongest practical ecosystem for PDF processing, schema-driven pipelines, CLI tooling, and testability. Python is also the right language for agent-friendly implementation here because the pipeline is artifact-heavy, IO-heavy, and benefits from strong data modeling more than raw runtime performance.

Schema/validation library

Pydantic v2 as the authoritative contract system, with JSON Schema generation exported from Pydantic models into a shared contracts package.

Reason:

Pydantic is the best fit for explicit artifact contracts and runtime validation.

It can generate JSON Schema from the same models, which lets the frontend consume generated types instead of re-defining contracts.

The pipeline should treat Pydantic models as the source of truth, not ad hoc JSON shape assumptions. Pydantic documents JSON Schema generation and states that generated schemas are compliant with JSON Schema Draft 2020-12.

Orchestration approach

Custom stage DAG runner inside the Python package, exposed via Typer CLI.

Reason:

This is a repo-local modular monolith, not a workflow-platform problem.

A small explicit stage runner is easier to reason about than Airflow/Prefect/Dagster.

Each stage should declare: name, version, input contracts, output contracts, cache scope, and work unit granularity.

CLI parses into PipelineConfig, but stage code never sees CLI objects.

Storage / artifact format

Filesystem artifact store, with:

JSON for manifests/config-like artifacts

JSONL for append-only collections like QAIssue and SearchDocument

binary files for extracted assets (.svg, .webp, .png)

orjson for serialization/deserialization

Reason:

Inspectable, diffable, portable, and easy for a solo builder.

Strong enough for immutable runs and resumability without bringing in a primary DB.

Optional derived SQLite can exist later for inspection, but not as the source of truth.

PDF extraction

PyMuPDF as the primary extractor.

Reason:

It exposes page text and images in structured forms, including block/line/span information and bounding boxes.

TextPage.extractDICT() / extractRAWDICT() and related Page.get_text("dict" / "rawdict") outputs preserve structure and include image and position detail, which is exactly what this system needs for semantic reconstruction and auditability.

LLM integration layer

Internal LlmGateway abstraction, with Gemini CLI gateway as the concrete provider implementation.

Reason:

Use a thin internal adapter, not a giant generic framework.

Keep provider-specific behavior explicit.

Google’s Gemini API supports structured JSON output with a JSON Schema subset; the docs also explicitly warn that syntactic schema compliance does not guarantee semantic correctness, so application-side validation is mandatory. That aligns perfectly with a bounded-LLM design and Pydantic validation.

Caching

Content-addressed filesystem cache, keyed by SHA-256 over:

stage version

input artifact hashes

document/rules/profile hashes

prompt hash

model ID

generation config

Reason:

Full transparency

Easy cache invalidation logic

Easy to inspect or nuke selectively

Works naturally with per-page and per-translation-unit resumability

Search indexing

Pagefind

Reason:

Perfect fit for a static reader.

No server component is required.

It supports multilingual indexing keyed off the document language, metadata capture, filters, result weighting, and sub-results by section headings. That makes it a strong choice for page/section search across multiple documents without adding a search backend.

Frontend framework

Next.js App Router + React + TypeScript + CSS Modules

Reason:

Static export is first-class.

Dynamic routes can be statically generated with generateStaticParams.

Route-based structure reduces ambiguity for agents.

Build-time rendering from typed content artifacts is a perfect fit.

Static export generates HTML per route and can be hosted on any static host.

Frontend state/data layer

Server Components for content routes, plus React context + reducer for UI state.

Reason:

Content should load at build time, not through ad hoc client fetches.

UI state is small: sidebar, theme, search dialog, glossary panel state.

No query library is needed for the main reader.

Search loads lazily on demand via Pagefind.

Testing stack

Backend: pytest, mypy, ruff
Frontend: Vitest, React Testing Library
E2E: Playwright

Reason:

Vitest is a modern Vite-native test runner and fits a Next/TS frontend toolchain well.

Playwright covers navigation, search, accessibility smoke checks, and visual regression in one stack.

Visual regression

Playwright screenshot assertions

Reason:

Built-in toHaveScreenshot()

Baseline-driven diffing

Good fit for static-reader pages and component states

The docs explicitly note that screenshots should be generated and compared in the same environment for consistency.

CI/CD

GitHub Actions for validation/build/test, Cloudflare Pages for static deployment.

Reason:

Good preview workflow

Static artifact deploy

Simple for a solo builder

No server runtime to manage

Observability/logging

structlog for structured JSON logs, OpenTelemetry for pipeline traces/metrics, Sentry for frontend runtime errors.

Reason:

Pipeline failures need run-level and stage-level traceability.

Reader runtime errors should surface from actual user sessions.

OpenTelemetry Python documents stable support for traces and metrics, which is the part that matters here.
3. Canonical Domain Model
Base artifact envelope

Every persisted artifact should be wrapped in a standard envelope.

class ArtifactEnvelope(BaseModel):
    schema_name: str
    schema_version: str
    artifact_id: str
    run_id: str
    stage: str
    stage_version: str
    created_at: datetime
    content_hash: str
    provenance: "Provenance"

This keeps contracts uniform and makes migration/resume logic straightforward.
DocumentConfig

Purpose
Human-authored declaration of a book/document and the profiles it uses.

Key fields

doc_id: str

slug: str

source_pdf: str

titles: {en: str, ru: str}

edition: str | None

source_locale: str = "en"

target_locale: str = "ru"

profiles: {rules: str, models: str, symbols: str, glossary: str, patches: str | None}

build: {route_base: str, include_in_catalog: bool}

navigation: {toc_overrides: list[...] | None}

render: {default_theme: str, figure_policy: str, page_label_offset: int | None}

Relationships

References one model profile, one rule profile, one symbol pack, one or more glossary packs, optional patch set.

Produces one DocumentManifest per source PDF version.

Versioning expectations

Versioned in git as authored config.

Changing it changes the config hash and invalidates affected downstream caches.

Owned by

Human-authored config layer

PipelineConfig

Purpose
Run-time execution policy.

Key fields

run_id: str

docs: list[str]

stages: {from: str | None, to: str | None, only: list[str] | None}

cache_mode: Literal["read_write", "read_only", "write_only", "off", "force_refresh"]

strict_mode: bool

max_workers: int

llm_concurrency: int

retry_policy: {max_attempts: int, backoff_seconds: list[int]}

artifact_root: Path

release_channel: Literal["dev", "preview", "prod"]

baseline_run_ref: str | None

Relationships

Combined with DocumentConfig to produce a ResolvedRunPlan.

Versioning expectations

Persisted per run in run_manifest.json

Not committed as a static file except defaults

Owned by

Orchestrator / CLI

DocumentManifest

Purpose
Immutable description of the actual source PDF observed by the system.

Key fields

doc_id

source_pdf_sha256

source_filename

file_size_bytes

page_count

pdf_metadata

page_dimensions: list[PageDimension]

source_outline: list[OutlineNode]

source_language_detected

ingest_profile_version

Relationships

Derived from DocumentConfig

Parent of all PageRecords for that run/source

Versioning expectations

Changes only if source PDF or ingest logic changes

Owned by

ingest_source stage

PageRecord

Purpose
Canonical page-level semantic representation.

Key fields

page_id: str (example: aeon-core:p0012)

doc_id: str

page_number: int

page_label: str

size_pt: {width: float, height: float}

rotation: int

blocks: list[Block]

assets: list[AssetRef]

section_path: list[str]

render_mode: Literal["semantic", "hybrid", "facsimile"]

source_fingerprint: str

provenance: Provenance

Relationships

Owns Block instances for one page

References page-local assets

Used to derive search, navigation, QA, and final rendering

Versioning expectations

Major schema version bumps if block model changes

Page identity remains stable within a source PDF version

Owned by

Structure by normalize_layout

Localized text fields later populated by merge_localization

Block

Purpose
Canonical semantic unit on a page.

Key fields

block_id: str (p0012.b007)

fingerprint: str

kind: Literal["heading","paragraph","list","list_item","callout","quote","figure","caption","table","divider"]

order: int

page_anchor: PageAnchor

section_path: list[str]

style_role: StyleRole

source_inlines: list[InlineNode]

localized_inlines: dict[str, list[InlineNode]] # keyed by locale

children: list[Block] | None

payload: dict[str, Any]

layout_hints: LayoutHints

provenance: Provenance

Relationships

Belongs to a PageRecord

May reference Assets or Symbols

May contain nested list items or table payloads

Versioning expectations

Discriminated union versioned centrally

kind additions require schema version bump

Owned by

Shape: normalize_layout

Text localization: translate + merge_localization

Glossary annotations: enrich_content

Asset

Purpose
Binary or logical page asset extracted from PDF.

Key fields

asset_id: str

doc_id: str

page_number: int

kind: Literal["image","vector","symbol_glyph","page_crop","table_fallback"]

bbox_pt: [float, float, float, float]

source_ref: str # xref or vector signature

sha256: str

mime_type: str

width_px: int

height_px: int

derivatives: list[DerivativeRef]

anchor: AssetAnchor

alt_text: dict[str, str]

render_policy: Literal["inline","block","lightbox","decorative","hidden"]

Relationships

Referenced by blocks or symbol resolution

Exported into the site bundle

Versioning expectations

Stable by content hash

Derivatives can be regenerated without changing logical identity

Owned by

extract_primitives and resolve_assets_symbols

Symbol

Purpose
Canonical symbol/icon definition.

Key fields

symbol_id: str

pack_id: str

label_en: str

label_ru: str

aliases: list[str]

svg_path: str

alt_text: str

detection: {image_hashes: list[str], vector_signatures: list[str], text_tokens: list[str]}

render_component: str

search_tokens: list[str]

Relationships

Referred to by inline symbol nodes or asset resolution

Shared across documents

Versioning expectations

One canonical symbol registry per pack

Changes are explicit config changes, never generated ad hoc

Owned by

Symbol pack config

GlossaryTerm

Purpose
Canonical terminology entry.

Key fields

term_id: str

pack_id: str

en_canonical: str

en_aliases: list[str]

ru_preferred: str

ru_variants: list[str]

lock_translation: bool

link_policy: Literal["always","first_only","never"]

doc_scope: list[str] | ["*"]

definition_ru: str

definition_en: str | None

notes: str | None

Relationships

Used during translation planning, validation, linking, and search enrichment

Versioning expectations

Canonical glossary data is authored and versioned in config

Variants are deterministic data, not frontend regex hacks

Owned by

Glossary pack config

QAIssue

Purpose
Machine-readable QA finding.

Key fields

issue_id: str

fingerprint: str

run_id: str

doc_id: str

rule_id: str

severity: Literal["error","warning","review","info"]

location: IssueLocation

message: str

evidence: dict[str, Any]

autofix: Literal["none","safe","review"]

source_artifact_ref: str

introduced_in_run: str

status_vs_baseline: Literal["new","existing","resolved","regressed"] | None

Relationships

References PageRecord, Block, InlineNode, Asset, or document-level entities

Versioning expectations

Stable schema; new rule evidence fields allowed additively

Owned by

QA stage

Sketch
class IssueLocation(BaseModel):
    scope: Literal["document", "page", "block", "inline", "asset", "search"]
    page_number: int | None = None
    block_id: str | None = None
    inline_id: str | None = None
    asset_id: str | None = None
    bbox_pt: tuple[float, float, float, float] | None = None

Provenance

Purpose
Lineage and reproducibility metadata.

Key fields

source_pdf_sha256: str

source_page_number: int | None

source_span_refs: list[SourceSpanRef]

parent_artifact_ids: list[str]

created_by_stage: str

stage_version: str

run_id: str

config_hashes: dict[str, str]

llm_call: LlmCallRef | None

notes: dict[str, Any]

Relationships

Embedded in every artifact envelope and every IR entity that can be traced

Versioning expectations

Extend additively

Never optional at artifact level

Owned by

Every stage writes/extends provenance

BuildArtifact

Purpose
Manifest entry for a deployable output file.

Key fields

artifact_id: str

kind: Literal["page_json","doc_manifest_json","glossary_json","asset","sprite","static_html","search_index","css","js"]

doc_id: str | None

locale: str | None

relative_path: str

media_type: str

content_hash: str

byte_size: int

source_refs: list[str]

Relationships

Listed in ReleaseManifest

Points back to PageRecords / SearchDocuments / assets

Versioning expectations

Content-hash stable

Not edited in place

Owned by

export_site_bundle, build_reader, index_search

SearchDocument

Purpose
Canonical section-level search unit.

Key fields

search_id: str

doc_id: str

locale: str

url: str

page_number: int

anchor_id: str

title: str

heading_path: list[str]

body_text: str

filters: dict[str, list[str] | str]

metadata: dict[str, str]

weight: float

source_block_ids: list[str]

Relationships

Derived from localized PageRecords

Exported to search-related bundle artifacts and mirrored into HTML metadata/weights

Versioning expectations

Stable additive schema

Owned by

build_navigation_and_search

Supporting types I would also define immediately

These are not optional in practice:

InlineNode

SourceSpanRef

PageAnchor

AssetAnchor

TranslationUnit

TranslationResult

NavigationTree

PatchSet

RunManifest

StageManifest

ReleaseManifest

4. End-to-End Pipeline Design
Pipeline overview
DocumentConfig + PipelineConfig
  -> resolve_run
  -> ingest_source
  -> extract_primitives
  -> collect_evidence (v3 only)
  -> resolve_page_ir (v3 only)
  -> normalize_layout
  -> resolve_assets_symbols
  -> plan_translation
  -> translate_units
  -> merge_localization
  -> enrich_content
  -> evaluate_qa
  -> apply_safe_fixes (not implemented — see Stage 10 below)
  -> export_site_bundle
  -> build_reader
  -> index_search
  -> package_release

The pipeline is explicitly staged, artifact-driven, and resume-capable.
Stage 0 — resolve_run

Input contract

DocumentConfig

PipelineConfig

referenced profiles (model, rules, symbols, glossary, patches)

Output contract

RunManifest skeleton

resolved config hashes

stage plan

Responsibilities

resolve all references

validate that profiles exist

compute config/prompt/profile hashes

create run directory structure

Deterministic vs LLM

fully deterministic

Failure modes

missing profile

duplicate doc_id

invalid YAML/JSON config

Retry/resume

no retry

rerun creates or resumes run manifest

Caching

none

Metrics

config resolution time

docs selected

Persist

run_manifest.json

resolved_config.json

Stage 1 — ingest_source

Input contract

ResolvedRunPlan

source PDF file

Output contract

DocumentManifest

Responsibilities

hash the source PDF

record metadata, page count, sizes, bookmarks/outlines

snapshot source filename and metadata

optionally copy or hardlink PDF into run storage

Deterministic vs LLM

deterministic

Failure modes

file missing

corrupted PDF

unreadable metadata

Retry/resume

whole-doc retry

usually fail fast

Caching

keyed by source_pdf_sha256 + ingest_stage_version

Metrics

ingest duration

page count

file size

Persist

01_ingest/document_manifest.json

01_ingest/source.pdf (or reference)

Stage 2 — extract_primitives

Input contract

DocumentManifest

source PDF

Output contract

one ExtractedPage artifact per page

extracted binary assets

lightweight page previews (optional debug)

Responsibilities

read page text primitives from PyMuPDF

preserve spans, fonts, block order, bboxes

extract images/vector info

store raw page primitives with exact source refs

Deterministic vs LLM

deterministic

Failure modes

page parse exception

corrupt embedded image

unsupported vector edge case

Retry/resume

page-level retry only

failed pages tracked individually

resume skips successful pages

Caching

page-level cache by:

source_pdf_sha256

page_number

extract_stage_version

extract_profile_hash

Metrics

pages/sec

text blocks/page

spans/page

images/page

vector objects/page

Persist

02_extract/pages/p0001.json

02_extract/assets/...

02_extract/manifest.json

Stage 2a — collect_evidence (v3 only)

Skips automatically when `architecture` is not `"v3"`.

Input contract

ExtractedPage (from stage 2)

Output contract

CanonicalPageEvidence

PrimitivePageEvidence

Responsibilities

build normalized page metadata and primitive evidence from extraction artifacts

subtract document furniture before downstream topology

emit canonical summary flags from post-furniture outputs

Deterministic vs LLM

deterministic

Persist

02a_evidence/pages/p0001.json

02a_evidence/manifest.json

Stage 2b — resolve_page_ir (v3 only)

Skips automatically when `architecture` is not `"v3"`.

Input contract

CanonicalPageEvidence

PrimitivePageEvidence

DocumentFurnitureProfile

PageRegionGraph

PageReadingOrder

DocumentAssetRegistry

Output contract

ResolvedPageIR

Responsibilities

resolve page regions, reading order, assets, entities, and confidence from evidence

produce a semantic-ready intermediate representation for downstream block building

Deterministic vs LLM

deterministic

Persist

02b_resolve_ir/pages/p0001.json

02b_resolve_ir/manifest.json

Stage 3 — normalize_layout

Input contract

ExtractedPage

rule profile

optional patch set

Output contract

source-side PageRecord

Responsibilities

determine reading order

segment lines into semantic blocks

detect headings, paragraphs, lists, callouts, captions, tables

assign stable block IDs and fingerprints

attach section paths where inferable

normalize wrapped text without changing semantics

apply deterministic layout overrides from patch set

Deterministic vs LLM

deterministic

Failure modes

ambiguous block classification

invalid block nesting

table extraction too weak for semantic rendering

Retry/resume

page-level rerun

ambiguous pages can be downgraded to hybrid render mode instead of blocking the entire run

Caching

page-level cache by:

extracted page hash

normalize stage version

rule profile hash

patch set hash

Metrics

block count by kind

heading detection confidence

list detection rate

hybrid/facsimile fallback count

Persist

03_normalize/pages/p0001.json

03_normalize/manifest.json
Stage 4 — resolve_assets_symbols

Input contract

normalized PageRecord

extracted assets

symbol pack

Output contract

enriched PageRecord

normalized Asset records

symbol occurrence map

Responsibilities

dedupe extracted assets

classify inline icons into canonical symbols

generate asset derivatives

assign asset anchors and render policies

connect figures/captions/assets

Deterministic vs LLM

deterministic

Failure modes

unresolved symbol

duplicate symbol matches

orphan caption or asset

Retry/resume

page-level rerun

Caching

page-level cache by:

normalized page hash

symbol pack hash

asset stage version

Metrics

symbol resolution rate

unresolved assets

figure-caption pairing rate

Persist

04_assets/pages/p0001.json

04_assets/assets/*.json

binary derivatives

Stage 5 — plan_translation

Input contract

enriched source-side PageRecords

glossary pack(s)

translation memory

model profile

target locale

Output contract

TranslationUnit artifacts

exact-cache hits

untranslated node list

Responsibilities

collect text-bearing inline nodes

preserve non-text nodes (symbols, anchors, refs)

freeze glossary-locked terms into placeholders

group nodes into bounded semantic units

attach context: heading path, nearby heading text, relevant glossary subset

skip units already satisfied by exact translation memory

Deterministic vs LLM

deterministic

Failure modes

conflicting term locks

overlarge units

invalid placeholder mapping

Retry/resume

unit-level rerun

Caching

deterministic planner cache by page hash + glossary/profile hash

Metrics

units created

cache/TM hit rate

avg chars per unit

Persist

05_translation_plan/units/u000001.json

05_translation_plan/index.json

Stage 6 — translate_units

Input contract

TranslationUnit set

model profile

prompt bundle

Output contract

TranslationResult per unit

raw LLM call metadata

failed unit records

Responsibilities

call LLM only for units not already satisfied

require structured JSON output

validate shape and semantic invariants

record reproducibility metadata

Deterministic vs LLM

LLM-driven

Failure modes

API/network failure

invalid structured output

missing/extra node IDs

placeholder corruption

glossary lock violation

unacceptable language quality heuristics

Retry/resume

retry sequence:

same request retry

smaller unit split

fallback model profile

mark unresolved and continue run in non-release mode

unit-level resume

Caching

by:

translation unit content hash

model ID

prompt hash

generation config hash

target locale

stage version

Metrics

token usage

latency

cost estimate

invalid output rate

placeholder preservation rate

fallback rate

Persist

06_translate/results/u000001.json

06_translate/failures/u000123.json

06_translate/calls/call_*.json
Stage 7 — merge_localization

Input contract

source-side PageRecords

TranslationResults

glossary pack

Output contract

localized PageRecords

Responsibilities

merge translated inline text back into exact nodes

restore locked terms/placeholders

compute localized headings and section paths

detect untranslated English leakage

attach deterministic glossary link annotations based on predeclared term variants

produce localized alt text placeholders where needed

Deterministic vs LLM

deterministic

Failure modes

missing translation for required node

placeholder mismatch

invalid localized inline sequence

glossary linker collisions

Retry/resume

page-level rerun after translation unit fixes

Caching

by page + translation result hashes + glossary hash

Metrics

translated node coverage

English leakage count

glossary link density

localized heading count

Persist

07_localize/pages/p0001.json

Stage 8 — enrich_content

Input contract

localized PageRecords

DocumentManifest

glossary pack

Output contract

NavigationTree

SearchDocument set

glossary index

document landing metadata

Responsibilities

build TOC/navigation from heading blocks

derive canonical URLs and DOM anchors

build section-level search units

generate doc summary metadata for catalog

compute Pagefind weights/filters/metadata source fields

Deterministic vs LLM

deterministic

Failure modes

broken heading hierarchy

duplicate anchors

empty search units

Retry/resume

doc-level rerun, but fast

Caching

by localized page hashes + nav/search stage version

Metrics

nav nodes

search docs

empty-section rate

duplicate-anchor count

Persist

08_enrich/navigation.json

08_enrich/search_documents.jsonl

08_enrich/glossary_index.json

Stage 9 — evaluate_qa

Input contract

localized pages

navigation

search docs

manifests

baseline run ref (optional)

Output contract

QAIssue JSONL

qa_summary.json

qa_by_page.json

qa_delta.json

Responsibilities

run deterministic rules

classify severity

compute acceptance status

compare against baseline accepted run

Deterministic vs LLM

deterministic

Failure modes

rule exception

broken schema on input artifacts

Retry/resume

doc-level rerun

Caching

by inputs + rules hash + baseline hash

Metrics

issue counts by severity/rule

new vs resolved issues

acceptance result

Persist

09_qa/issues.jsonl

09_qa/summary.json

09_qa/delta.json

derived markdown/html reports
Stage 10 — apply_safe_fixes (planned, not in registry)

Input contract

localized pages

QA issues

patch set

Output contract

corrected pages

PatchSuggestion records

fix audit log

Responsibilities

apply only deterministic, idempotent, safe fixes

never silently mutate on fuzzy confidence

emit review suggestions instead of speculative edits

Deterministic vs LLM

deterministic in the default architecture

any LLM-assisted review suggestions are separate tools, not release-path stages

Failure modes

conflicting patch

non-idempotent fix attempt

post-fix schema invalidation

Retry/resume

page-level rerun

Caching

page hash + issue fingerprints + patch hash

Metrics

fixes applied

fix acceptance rate

remaining issue count

Persist

10_fix/pages/p0001.json

10_fix/suggestions.jsonl

10_fix/audit.json

Stage 11 — export_site_bundle

Input contract

final accepted pages

assets

nav

glossary

search docs

QA summary

Output contract

SiteBundle directory for frontend consumption

BuildArtifact manifest

Responsibilities

export doc bundle in frontend-ready shape

emit catalog manifest

emit icon sprite / asset map

emit glossary/doc/page JSON

copy only selected derivative assets

Deterministic vs LLM

deterministic

Failure modes

schema mismatch

missing asset reference

invalid URL generation

Retry/resume

doc-level rerun

Caching

by final page hashes + export stage version

Metrics

bundle size

asset count

page JSON count

Persist

11_export/site_bundle/<doc_id>/...

11_export/build_artifacts.json

Stage 12 — build_reader

Input contract

exported site bundles

reader app source

Output contract

static site output

Responsibilities

statically generate all routes

embed metadata/filter/weight hints for Pagefind

validate route coverage for all pages/docs

Deterministic vs LLM

deterministic

Failure modes

React/Next render error

missing generated content file

contract mismatch between bundle and renderer

Retry/resume

full site rebuild

Caching

handled by frontend build tooling; not pipeline-owned

Metrics

build duration

HTML size by route

JS bundle sizes

Persist

12_site/out/...

Stage 13 — index_search

Input contract

static HTML site

Output contract

Pagefind index

Responsibilities

run Pagefind

verify index presence

run lightweight search smoke query

attach site-wide or doc-level filters

Deterministic vs LLM

deterministic

Failure modes

index build error

missing metadata/filter tags

smoke query failure

Retry/resume

rerun index build only

Caching

by built HTML hash

Metrics

index size

chunks created

query smoke pass/fail

Persist

13_search/pagefind/...
Stage 14 — package_release

Input contract

static site

search index

QA acceptance

Output contract

deployable bundle

ReleaseManifest

deployment metadata

Responsibilities

enforce release gate

package files

publish to static host

record release provenance

Deterministic vs LLM

deterministic, except remote publish side effect

Failure modes

release gate fail

host upload fail

Retry/resume

rerun packaging/deploy only

Caching

none

Metrics

release duration

deployed artifact bytes

deployment target info

Persist

releases/<doc_id>/<release_id>/...

deployment receipt

5. Canonical Intermediate Representation

Yes: this system needs a block-preserving IR, and it should be the canonical contract of the entire product.

IR principles

Page-sharded

one PageRecord per page

easy partial reruns

easy visual/QA mapping

Semantic first, geometric retained

semantic block kinds drive rendering

original geometry remains in anchors/provenance for audit/debug

Text is node-based, not blob-based

translatable text lives in inline nodes

symbols, references, and assets are separate nodes

Localized text is additive

source text remains

localized text is added by locale key

this makes QA, debugging, and future multi-locale support easier

Markdown is not canonical

any markdown is derived from IR for debug/export only

Block types

Use this exact initial block set:

heading

paragraph

list

list_item

callout

quote

figure

caption

table

divider

Do not introduce dozens of niche block kinds in v1. Keep the core set tight and expressive.

Inline node types

Use this exact initial inline set:

text

symbol

xref

line_break

emphasis

That is enough for a rulebook reader without inventing a full rich-text DSL.

Stable IDs

Every block and inline node gets both:

a human-stable local ID

a content fingerprint

Example:

block_id = "p0012.b007"

inline_id = "p0012.b007.i003"

fingerprint = sha256(page_no | rounded_bbox | kind | normalized_source_text | source_span_refs)

Use the readable ID for rendering and links. Use the fingerprint for diffing, QA baselines, and cache lineage.

This dual-ID approach matters because block order can shift when layout rules improve, but content fingerprints help identify continuity across runs.
Page anchoring

Each block must carry:

class PageAnchor(BaseModel):
    page_number: int
    bbox_pt: tuple[float, float, float, float]
    reading_order: int
    source_span_refs: list[SourceSpanRef]

This gives:

exact issue localization

screenshot overlays

auditability back to source PDF

deterministic DOM anchor generation

Asset anchoring

Each asset must have one of:

inline — symbol or small graphic inline with text

after_block — figure/caption paired with a host block

page_region — large page-local asset with no semantic host block

fallback_render — asset used because semantic reconstruction was not good enough

class AssetAnchor(BaseModel):
    mode: Literal["inline", "after_block", "page_region", "fallback_render"]
    host_block_id: str | None = None
    page_bbox_pt: tuple[float, float, float, float] | None = None
    placement_hint: Literal["inline", "full_width", "float_right", "lightbox"] = "full_width"
IR sketch
class TextInline(BaseModel):
    kind: Literal["text"] = "text"
    inline_id: str
    source_text: str
    localized_text: dict[str, str] = Field(default_factory=dict)
    glossary_hits: list[str] = Field(default_factory=list)

class SymbolInline(BaseModel):
    kind: Literal["symbol"] = "symbol"
    inline_id: str
    symbol_id: str
    alt_text: dict[str, str]

class XrefInline(BaseModel):
    kind: Literal["xref"] = "xref"
    inline_id: str
    target_anchor_id: str
    label: dict[str, str]

InlineNode = Annotated[
    TextInline | SymbolInline | XrefInline,
    Field(discriminator="kind")
]

class Block(BaseModel):
    block_id: str
    fingerprint: str
    kind: str
    order: int
    page_anchor: PageAnchor
    section_path: list[str]
    source_inlines: list[InlineNode]
    localized_inlines: dict[str, list[InlineNode]] = Field(default_factory=dict)
    children: list["Block"] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    layout_hints: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance
How translation works without destroying structure
This is the heart of the design.

For each text-bearing inline node:

keep the block tree exactly as-is

extract only the TextInline nodes into TranslationUnits

preserve SymbolInline and XrefInline nodes untouched

freeze glossary-locked terms into placeholders before model input

send the model a list of {inline_id, source_text} pairs plus local context

receive {inline_id, translated_text} pairs only

validate

merge translated strings back into the exact inline slots

The model never sees freedom to decide:

whether something is a heading

whether something is a list

where captions go

whether markdown should be emitted

whether symbols should be rewritten

That is why this design is robust.

How QA refers to exact locations

Every issue references:

document

page

block

inline or asset if applicable

bbox if known

So a QA issue can say:

page=12

block_id="p0012.b007"

inline_id="p0012.b007.i003"

bbox=[72.1, 418.0, 510.4, 463.7]

This enables:

precise console/HTML reports

screenshot overlays

regression diffing by issue fingerprint

patch suggestions against exact nodes

How rendering derives HTML / markdown / search text

HTML / React
Primary output. The reader app renders block unions to semantic components:

heading -> <h1..h6>

paragraph -> <p>

list -> <ul>/<ol>

table -> <table> or fallback figure

figure -> <figure><img/><figcaption/>

Markdown
Optional debug export only:

generated from IR

never consumed by the site

useful for spot inspection or external sharing

Search text
Derived deterministically from:

heading text

paragraph text

list item text

captions

optional symbol alt labels

glossary terms as metadata, not UI hacks

Hybrid/facsimile escape hatch

For pages or blocks that are too graphically complex for quality semantic rendering, the IR should support:

render_mode = "hybrid" at page level

payload["fallback_asset_id"] at block level

This gives you a practical release valve without poisoning the whole system with image-only behavior.

6. LLM Strategy
Principle

Use LLMs only where semantic transformation is needed.

Default release-path LLM usage

Only one stage uses an LLM in the default architecture:

translate_units

Everything else is deterministic.

Optional non-release-path LLM tools

Allowed later as offline tools, not default pipeline stages:

terminology review suggestion tool

human-review patch suggestion tool

comparative translation benchmark runner

But not required for v1.

What the LLM should never do

The LLM should not:

decide structure

emit markdown

emit HTML

repair layout

invent headings

classify symbols

rewrite navigation

emit final site content blobs

All of those are code-owned.

Translation unit design

A TranslationUnit should contain:

unit_id

doc_id

page_number

section_path

style_hint (heading/body/callout/table-cell)

glossary_subset

locked_terms

text_nodes: list[{inline_id, source_text}]

context_before / context_after (small bounded strings)

constraints

Unit sizing:

group by semantic locality, not page

target roughly 300–1200 source characters per unit

never mix unrelated headings/sections in one unit

This gives consistency without turning the prompt into page soup.

Prompt design principles

System prompt

translation role

target audience

style guide

glossary rules

strict rule: translate text only, preserve IDs, do not add/remove entries

Input payload

machine-readable JSON

no natural-language wrapper beyond instructions

include only the minimum needed context

Output

strict JSON

one entry per input node

same IDs only

Example target shape:

{
  "unit_id": "u_0012_03",
  "translations": [
    { "inline_id": "p0012.b007.i001", "ru_text": "..." },
    { "inline_id": "p0012.b007.i002", "ru_text": "..." }
  ]
}
Structured output strategy
Primary provider path:

use Gemini structured output mode with JSON MIME type and JSON Schema

validate returned JSON with Pydantic

reject any schema-valid but semantically invalid response

Gemini’s structured output docs explicitly say:

it supports a subset of JSON Schema

syntactically valid JSON is not enough

application-side validation is still required.

That is exactly how this system should behave.

Validation strategy

A translation result is accepted only if all of these pass:

JSON parses into the expected Pydantic model

unit_id matches

returned inline_ids exactly match requested inline_ids

no extra entries

all locked placeholders preserved

no banned control characters

language sanity checks pass

glossary lock rules pass

per-node length ratio is within sane bounds unless explicitly exempt

optional English leakage threshold passes

If validation fails, the result is not merged.

Model abstraction layer

Implement this interface:

class LlmProvider(Protocol):
    name: str

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        ...

Concrete implementations:

GeminiCliGateway (v1)

OpenAIProvider (optional later)

And one wrapper:

class LlmGateway:
    def translate_unit(self, unit: TranslationUnit, profile: ModelProfile) -> TranslationResult: ...

This keeps provider switching explicit without adopting a generic dependency you do not need.

Provider switching

Provider switching is by model profile, not by changing stage code.

Example model profile:

profile_id: translate-default
provider: gemini
model: gemini-flash-class
fallback_provider: gemini
fallback_model: gemini-pro-class
temperature: 0.1
top_p: 0.9
max_output_tokens: 4096
prompt_bundle: translate-v1

Later, an openai profile can be added without changing stage semantics.

Caching keys

LLM cache key:

sha256(
  translate_stage_version |
  unit_content_hash |
  prompt_hash |
  glossary_subset_hash |
  model_profile_hash |
  target_locale
)

Do not key only by raw text. Context and glossary matter.

Reproducibility metadata

Persist with every LLM result:

provider

model ID

model profile ID

SDK name/version

prompt bundle ID and hash

generation config

request hash

response hash

token usage

latency

retry count

timestamp

That is enough to reproduce or benchmark later.

Fallback behavior

For a failed unit:

retry same request once

retry with smaller chunk split

retry with fallback model profile

if still bad:

emit unresolved QAIssue

keep pipeline resumable

block release if unresolved issues remain

Do not silently pass through malformed results.

Benchmarking models by stage

Create a fixed benchmark corpus of representative translation units:

headings

dense rules text

glossary-heavy paragraphs

list-heavy sections

symbol-bearing lines

table cells

For each model/profile, measure:

validation pass rate

placeholder preservation

glossary lock rate

QA issue count after merge

human review score on a small sampled set

cost/token

latency

Persist benchmark outputs under benchmarks/translate/<date>/<profile>.json.

How to minimize formatting hallucinations

This architecture minimizes them by design:

no markdown output

no HTML output

no structure decisions by model

no page-wide blobs

strict schema output

exact ID mapping

placeholder locking for terms/symbols

deterministic renderer downstream

If the LLM can only fill ru_text fields, it cannot hallucinate document structure.

7. QA and Verification Architecture
Principle

QA is its own product subsystem.

The source of truth is:

issues.jsonl

summary.json

delta.json

Human-readable reports are derived artifacts.

QAIssue schema
class QAIssue(BaseModel):
    issue_id: str
    fingerprint: str
    run_id: str
    doc_id: str
    rule_id: str
    severity: Literal["error", "warning", "review", "info"]
    location: IssueLocation
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    autofix: Literal["none", "safe", "review"] = "none"
    source_artifact_ref: str
    status_vs_baseline: Literal["new", "existing", "resolved", "regressed"] | None = None
Rule engine structure
Each rule is a pure function module:

class Rule(Protocol):
    rule_id: str
    scope: Literal["document", "page", "block", "inline", "asset", "search"]
    default_severity: str

    def evaluate(self, inputs: RuleInputs) -> Iterable[QAIssue]:
        ...

Rule groups:

schema_rules

layout_rules

translation_rules

symbol_rules

render_rules

navigation_rules

search_rules

release_rules

Severity model

Use exactly four levels:

error — release blocker

warning — allowed but counted

review — human attention recommended; release-blocking in strict mode

info — non-blocking metric/report signal

Do not overcomplicate severity in v1.

Pass/fail logic

A document is accepted when:

zero error issues

zero unresolved required translation units

zero unresolved symbol mappings

zero broken page routes / anchor collisions

zero schema validation failures

warnings are within configured budget

no regressed issue budget against baseline

Release mode should fail on:

any error

any unresolved review if strict_mode=true

Page-level vs block-level issues

Document-level

missing manifest field

duplicate routes

search index missing

glossary pack conflict

Page-level

no heading on page

no visible content

broken render mode fallback

asset coverage gap

Block-level

paragraph too long

malformed list nesting

missing caption host

unresolved glossary lock

untranslated text node

Inline-level

placeholder corruption

mixed-language leakage

broken xref label

Asset-level

unresolved symbol

missing derivative

empty alt text on non-decorative asset
Acceptance criteria

Hard gates:

all artifacts validate

all page routes build

all search docs generate

all required assets exist

all symbols resolve

all translatable text nodes are localized

Soft gates:

paragraph length warning budgets

glossary link density

manual review suggestions

section title style warnings

Report generation

Canonical machine-readable outputs:

qa/issues.jsonl

qa/summary.json

qa/by_page.json

qa/delta.json

Derived outputs:

qa/report.md

qa/report.html

qa/page_overlays/ screenshots with issue boxes

qa/top_regressions.md

The markdown/HTML reports must be rendered from the JSON, never authored directly.

Autofix design

There are three fix classes:

Normalization fixes
Applied before QA as part of deterministic normalization.

Safe post-QA fixes
Idempotent deterministic changes that are known-safe. Example:

merge accidental line wraps

normalize repeated whitespace

convert bullet glyph pattern to list block when confidence is absolute

Review suggestions
Emitted as PatchSuggestion records, not auto-applied. Example:

reclassify ambiguous heading

use figure fallback for a weakly extracted table

glossary variant conflict

Rule outputs can attach:

autofix="safe" or autofix="review"

a suggested patch payload

Regression tracking across runs

Every accepted run becomes an optional baseline.

Compare new run vs baseline on:

issue fingerprints

issue counts by rule/severity

search document counts

symbol resolution rate

hybrid/facsimile fallback count

translation failure rate

Persist:

qa/delta.json

This makes refactors measurable instead of anecdotal.

8. Frontend / Reader Architecture
Reader design principle

The frontend is a typed static document renderer, not a content repair engine.

It should not parse markdown, repair broken symbols, or invent glossary links. It renders a validated bundle.

App structure

Use Next.js App Router with route groups:

/ — library/catalog landing

/docs/[docId] — document landing page

/docs/[docId]/page/[pageNo] — reader page

/docs/[docId]/glossary — document glossary

/docs/[docId]/search — optional dedicated search route, though modal search is preferred

/404 — static not found

Primary navigation model:

page routes

anchor links to blocks/headings within page

sidebar TOC from generated navigation tree

Major components

Top-level:

AppShell

SiteHeader

DocLayout

DocSidebar

TocTree

SearchDialog

ThemeProvider

RouteErrorBoundary

Reader content:

PageView

BlockRenderer

InlineRenderer

HeadingBlock

ParagraphBlock

ListBlock

CalloutBlock

FigureBlock

TableBlock

CaptionBlock

SymbolInline

GlossaryLink

XrefLink

Support:

GlossaryDrawer

PageNav

FigureLightbox

SearchResults

EmptyState

ErrorPanel
Data flow

At build time

Next reads generated site bundle JSON

generateStaticParams() enumerates docs/pages

each page route renders static HTML from typed PageRecord data

At runtime

minimal client hydration for:

theme

sidebar toggle

search dialog

glossary drawer/tooltips

figure lightbox

No runtime content fetch is required for the main page render path.

Rendering pipeline
PageRecord JSON
  -> BlockRenderer (switch on block.kind)
  -> InlineRenderer (switch on inline.kind)
  -> semantic HTML + stable DOM ids + Pagefind metadata

This is deterministic and testable.

No dangerouslySetInnerHTML in normal content rendering.

Search flow

Use Pagefind lazily.

Flow:

user opens search

app dynamically imports Pagefind JS

current doc filter is applied by default

results show:

title

excerpt

doc title

page number

optional sub-result heading

clicking result navigates to /docs/[docId]/page/[pageNo]#anchor

Pagefind supports:

sub-results by heading IDs

metadata return

filters

weighting.

Glossary linking

Glossary linking is offline.

The bundle should already contain which inline nodes map to which glossary terms. The frontend only renders that data.

Rendering options:

inline underline + tooltip on hover/focus

click opens GlossaryDrawer

glossary page lists all terms for the current document

Do not perform runtime regex linking.

Symbol rendering

Symbols come from the canonical symbol pack:

inline symbols render from SVG sprite/component by symbol_id

block-level symbols/figures use exported derivatives

all symbols have consistent labels and alt text from one source

This makes symbol behavior uniform across all documents.

Caching / prefetching

rely on Next route prefetching for page navigation

prefetch next/previous page routes

lazy-load search code on first search open

lazy-load lightbox code only when a figure is opened

keep glossary data in doc-level chunk, not page-level duplication

Error boundaries

Use:

route-level error boundary

search modal boundary

figure/lightbox boundary

document-shell boundary

React documents that rendering errors are handled by Error Boundaries, and without them a render error can remove UI from the screen. React also documents lazy() for deferred component loading with cached results. That is exactly how the reader should isolate risky UI and heavy features.
Performance strategy

static HTML for content routes

minimal hydration

no client markdown parser

no client content repair

route-based code splitting

lazy search

lazy figure lightbox

CSS Modules + CSS custom properties

image derivatives sized for reader usage

hybrid/fallback pages allowed for pathological layouts

Accessibility

Non-negotiable baseline:

semantic heading hierarchy

keyboard-navigable sidebar/search/dialog

visible focus styles

alt text for non-decorative figures

glossary interactions accessible by keyboard and screen reader

skip-to-content link

reduced motion support

color contrast checked in both themes

Dark mode

Use CSS custom properties with:

prefers-color-scheme default

persisted user override

no theme-specific content logic

Internationalization readiness

Even though v1 outputs Russian only, build the reader as locale-ready:

locale field in bundle

localized labels from document/site bundle

route helpers support locale segment later if needed

IR stores source text and localized text separately

That gives a future English/Russian toggle without redesigning the core model.

9. Repository / Folder Structure

I recommend one monorepo with explicit boundaries.
/
├─ apps/
│  └─ reader/
│     ├─ app/
│     │  ├─ page.tsx
│     │  ├─ layout.tsx
│     │  ├─ docs/
│     │  │  └─ [docId]/
│     │  │     ├─ page.tsx
│     │  │     ├─ glossary/
│     │  │     │  └─ page.tsx
│     │  │     └─ page/
│     │  │        └─ [pageNo]/
│     │  │           └─ page.tsx
│     ├─ components/
│     ├─ lib/
│     ├─ styles/
│     ├─ generated/              # gitignored site bundle input
│     ├─ public/
│     ├─ next.config.ts
│     ├─ package.json
│     └─ tsconfig.json
│
├─ packages/
│  ├─ pipeline/
│  │  ├─ src/aeon_reader_pipeline/
│  │  │  ├─ cli/
│  │  │  ├─ config/
│  │  │  ├─ models/
│  │  │  ├─ stages/
│  │  │  ├─ llm/
│  │  │  ├─ qa/
│  │  │  ├─ io/
│  │  │  ├─ cache/
│  │  │  ├─ migrations/
│  │  │  ├─ exporters/
│  │  │  └─ utils/
│  │  ├─ pyproject.toml
│  │  └─ README.md
│  │
│  └─ contracts/
│     ├─ jsonschema/             # generated from Pydantic
│     ├─ typescript/             # generated TS types
│     └─ README.md
│
├─ configs/
│  ├─ catalog.yaml
│  ├─ documents/
│  ├─ model-profiles/
│  ├─ rule-profiles/
│  ├─ symbol-packs/
│  ├─ glossary-packs/
│  └─ overrides/
│
├─ prompts/
│  ├─ translate/
│  │  ├─ v1/
│  │  │  ├─ system.j2
│  │  │  ├─ user_payload_schema.json
│  │  │  └─ response_schema.json
│  └─ review/
│
├─ tests/
│  ├─ fixtures/
│  │  ├─ pdf/
│  │  ├─ extracted/
│  │  ├─ normalized/
│  │  ├─ translated/
│  │  └─ site-bundles/
│  ├─ backend/
│  ├─ frontend/
│  ├─ e2e/
│  └─ visual/
│
├─ artifacts/                    # gitignored
│  ├─ cache/
│  ├─ runs/
│  ├─ releases/
│  └─ state/
│
├─ docs/
│  ├─ adr/
│  ├─ architecture/
│  └─ operator-guides/
│
├─ scripts/
├─ .github/workflows/
├─ Makefile
├─ package.json
├─ pnpm-workspace.yaml
├─ pyproject.toml
└─ README.md
Boundary rules

packages/pipeline owns all canonical schemas and artifact writers

packages/contracts is generated, not hand-authored

apps/reader never defines artifact shapes by hand

configs/ is the single source for manifests/profiles/packs/overrides

artifacts/ is never source code

tests/fixtures contains the benchmark/golden corpus for both pipeline and UI

10. Configuration and Single Sources of Truth
Document manifests

Human-authored document configs live in:

configs/documents/<doc_id>.yaml

Example:

doc_id: aeon-trespass-core
slug: aeon-trespass-core
source_pdf: sources/aeon-trespass-core.pdf

titles:
  en: Aeon Trespass: Core Rulebook
  ru: Aeon Trespass: Основной свод правил

source_locale: en
target_locale: ru

profiles:
  rules: rulebook-default
  models: translate-default
  symbols: aeon-core
  glossary: aeon-core
  patches: aeon-trespass-core

build:
  route_base: /docs/aeon-trespass-core
  include_in_catalog: true
Model selection

Model selection lives in:

configs/model-profiles/*.yaml

Not in code.

A document references a model profile ID. CLI may override profile for experimentation, but that override is written into run_manifest.json.

Thresholds and rules

All thresholds live in:

configs/rule-profiles/*.yaml

Not in functions.

Example:

heading detection ratios

paragraph length budgets

symbol confidence thresholds

release warning budgets

Symbol specs

Canonical symbol definitions live in:

configs/symbol-packs/*.yaml

This is the only source of truth for:

symbol IDs

labels

alt text

detection signatures

render mappings

Frontend icons and pipeline detection maps are generated from this pack.

Glossary data

Canonical glossary entries live in:

configs/glossary-packs/*.yaml

This is the only source for:

canonical terms

preferred Russian forms

allowed variants

lock policy

link policy

definitions

Translation constraints, glossary linking, and glossary UI all derive from this same pack.

Environment-specific config

Environment variables should be used only for:

API keys / credentials

host-specific paths if unavoidable

deploy target secrets

Do not put functional pipeline behavior in env vars.

Behavioral config belongs in repo files.

Multi-document support

Use a root catalog:

configs/catalog.yaml

Example:

documents:
  - aeon-trespass-core
  - aeon-trespass-expansion-1

groups:
  release-core:
    - aeon-trespass-core

This enables:

build one doc

build all docs

build a release group

Downstream derivation rules

Downstream systems derive, they do not duplicate:

output paths derive from doc_id

site titles derive from DocumentConfig

routes derive from route_base

model selection derives from model profile

symbol map derives from symbol pack

glossary UI derives from glossary pack

search filters derive from doc metadata and search documents

page labels derive from page records / manifest

accepted-run pointers derive from artifact state

11. Storage, Artifacts, and Versioning
Artifact strategy

Use immutable run directories.

artifacts/
  runs/<run_id>/<doc_id>/

Every stage writes to its own directory.

Example:

artifacts/runs/2026-03-11T153012Z/aeon-trespass-core/
  run_manifest.json
  01_ingest/
    document_manifest.json
  02_extract/
    manifest.json
    pages/p0001.json
    assets/...
  03_normalize/
    pages/p0001.json
  04_assets/
    pages/p0001.json
    assets/*.json
  05_translation_plan/
    units/*.json
  06_translate/
    results/*.json
    failures/*.json
    calls/*.json
  07_localize/
    pages/p0001.json
  08_enrich/
    navigation.json
    search_documents.jsonl
    glossary_index.json
  09_qa/
    issues.jsonl
    summary.json
    delta.json
    report.md
    report.html
  10_fix/
    pages/p0001.json
    suggestions.jsonl
  11_export/
    site_bundle/...
    build_artifacts.json
What is stored where

JSON

manifests

page records

navigation tree

glossary index

build artifacts

release manifest

run manifest

JSONL

QA issues

search documents

patch suggestions

benchmark results

Binary

source PDF snapshot

SVG/PNG/WebP derivatives

Pagefind index files

static site assets

No primary SQLite in v1

optional inspect.sqlite can be generated later for local analysis only

Naming conventions

run IDs: UTC timestamp based, e.g. 2026-03-11T153012Z

page files: p0001.json

unit files: u000123.json

asset files: <asset_id>.<ext>

release IDs: <doc_id>-<date>-<shortsha>

Content hashing

Every primary artifact gets:

content_hash in envelope

SHA-256 file hash in manifest

Cache keys should use:

stage version

input artifact hashes

config hashes

prompt hash

model profile hash

Not raw timestamps.

Schema versions

Every artifact includes:

schema_name

schema_version

Example:

PageRecord@1.0.0

QAIssue@1.0.0

SearchDocument@1.0.0

Migration strategy

Rules:

old runs are immutable

readers/build tools read current versions only

upcasters live in packages/pipeline/.../migrations/

explicit command:

reader-pipeline migrate-run --run <id> --to-current

Use upcasting for:

additive field changes

renamed fields

small shape shifts

Use hard break + re-run when:

IR semantics fundamentally changed

Run metadata

run_manifest.json should include:

run ID

started/finished times

status per stage

document config hash

rule profile hash

symbol pack hash

glossary pack hash

prompt bundle hash

model profile hash

source PDF hash

git commit

tool versions

cache hits/misses

QA acceptance result

Reproducibility

A run is reproducible if it records:

source PDF hash

all config/profile hashes

stage versions

prompt hashes

model IDs

generation settings

asset hashes

artifact hashes

That is the minimal sufficient set.

Resumability

Each stage manifest tracks work unit status.

Examples:

page statuses for extract/normalize/localize

unit statuses for translation

doc-level status for enrich/QA/export

Resume logic:

validate output artifact

skip if valid

rerun only missing/failed units

Partial reruns

Supported commands should include:

rerun one stage for one doc

rerun selected pages

rerun selected translation units

rebuild site from accepted bundle only

Examples:

... run --doc aeon-trespass-core --from normalize --pages 12-18

... run --doc aeon-trespass-core --only translate --units u0012_03,u0012_04

... build-site --doc aeon-trespass-core --from-export

Accepted run pointers

State lives under:

artifacts/state/
  accepted_runs.json
  baselines.json

Example:

current accepted run for a doc

current QA baseline for a doc

current published release per doc

Do not use symlinks as the primary mechanism.

12. Testing Strategy
Test pyramid
1. Schema / contract tests

What they verify:

every Pydantic model round-trips

generated JSON Schema matches model expectations

example artifacts validate

frontend generated types are refreshed and compile

Blocks CI:

yes

2. Pure unit tests

Backend:

hashing

ID generation

rule helpers

glossary linker

placeholder freezer/restorer

cache key builder

Frontend:

block renderer helpers

route helpers

search result formatting

theme reducer

Blocks CI:

yes

3. Stage integration tests

Run real stages against tiny fixture PDFs.

Must cover:

ingest

extract

normalize

assets/symbol resolution

translate with mocked provider

localize

QA

export

Blocks CI:

yes

4. Golden artifact tests

Use a representative corpus of fixture pages:

dense prose

list-heavy page

symbol-heavy page

figure/caption page

table page

weird edge case page

Compare:

normalized PageRecord

translated PageRecord

QAIssue output

SearchDocument output

exported bundle snippets

Blocks CI:

yes

5. LLM contract tests

Two kinds:

Offline deterministic

mocked/bad responses

schema failures

placeholder corruption

missing IDs

fallback behavior

Live smoke tests (nightly or manual)

one small corpus against actual provider/model profile

verify structured output still parses and quality floor holds

Blocks CI:

mocked tests yes

live tests no for normal PRs; yes for scheduled benchmark workflow

6. Frontend unit/component tests

Test:

BlockRenderer

InlineRenderer

GlossaryLink

TocTree

SearchDialog

route not-found behavior

error fallback rendering

Blocks CI:

yes

7. E2E tests

Playwright scenarios:

open catalog

open document

navigate page route

anchor link works

glossary open works

search finds result

next/previous navigation works

dark mode persists

keyboard navigation works

error boundary fallback shows for injected fault

Blocks CI:

yes

8. Screenshot / visual regression tests

Playwright on:

doc landing page

typical text page

symbol-heavy page

table/fallback page

glossary page

search dialog state

dark mode text page

Blocks CI:

yes on protected baseline set

baseline refresh allowed only via explicit approval

Playwright’s built-in screenshot assertions are the right primitive here.

What should block CI

Hard blockers:

lint failure

typecheck failure

schema generation drift

backend unit/integration/golden failure

frontend unit/component failure

Next static build failure

E2E failure

protected visual regression failure

sample-bundle QA acceptance failure

Non-blocking but reported:

live LLM benchmark drift

full-doc nightly build failures on non-release branches

13. CI/CD and Developer Workflow
Local dev loop

Use a single root Makefile as the stable operator and agent interface.

Core commands:

make bootstrap

make schemas

make test

make test-backend

make test-frontend

make e2e

make fixtures

make pipeline DOC=aeon-trespass-core TO=qa

make export DOC=aeon-trespass-core

make site-build

make site-dev

make inspect RUN=<run_id> DOC=<doc_id> PAGE=12

Under the hood:

Python via uv

frontend via pnpm

Validation commands

Suggested mappings:

make lint -> ruff + eslint

make typecheck -> mypy + tsc

make schemas -> regenerate contracts from Pydantic

make check-generated -> ensure no dirty diff after generation

make qa-fixtures -> run sample fixture pipeline to QA

Build commands

content-only:

uv run reader-pipeline run --doc <doc> --to export

site-only:

pnpm --filter reader build

full release:

make release DOC=<doc>

Artifact inspection workflow

A solo builder needs good inspection, not just logs.

Provide:
CLI inspector that prints page/block summaries

HTML QA report

page overlay screenshots keyed by issue

artifact browsing under run dirs

frontend dev mode against apps/reader/generated/

CI stages

Bootstrap

install Python and Node deps

Contracts

generate schemas/types

fail if checked-in generated files drift

Backend quality

lint

typecheck

unit tests

stage integration

golden artifacts

Frontend quality

lint

typecheck

unit/component tests

Fixture pipeline

build sample bundle

evaluate QA

Site build

static export

Pagefind index

E2E + visual

Playwright

Preview deploy

on PR or main branch

Release deploy

on tag or manual promotion after acceptance

Release / deploy flow

Recommended:

PRs -> preview deployment

merge to main -> full validation + preview/staging deployment

tagged release or manual workflow -> production deployment

A release should carry:

release manifest

accepted run ref

QA summary

git commit

doc IDs included

Failure triage approach

When CI fails, triage starts in this order:

run_manifest.json

qa/summary.json

qa/delta.json

stage-specific failures/*.json

screenshot diffs

static build logs

This gives coding agents a deterministic path to diagnosis.

Agent-friendly workflow rule

Every substantial change should touch one of:

ADR

schema

stage

renderer

rule

And CI should tell the agent exactly which contract drifted.

14. Implementation Roadmap
Phase 0 — Workspace and contracts

Objective
Create the repo, toolchain, contract system, and config skeleton.

Deliverables

monorepo skeleton

Python package + Next app

Pydantic models for core artifacts

generated JSON Schema + TS types

sample DocumentConfig, model profile, rule profile, symbol pack, glossary pack

root Makefile

Dependencies

none

Agent-independent work

schema models

config loader

contract generation

repo bootstrap

ADRs

Acceptance criteria

make bootstrap, make schemas, make test all work

sample configs validate

generated contracts compile in frontend

Phase 1 — Artifact runtime and stage registry

Objective
Build the pipeline runtime skeleton.

Deliverables

RunManifest

StageSpec

artifact IO layer

hash utilities

cache key builder

stage registry

CLI commands for run/inspect/resume

Dependencies

Phase 0

Agent-independent work

IO/caching

stage registry

CLI

run manifest serialization

Acceptance criteria

no-op demo pipeline can execute stages and persist manifests

resume logic skips valid prior outputs

Phase 2 — PDF ingest and primitive extraction

Objective
Get deterministic source extraction working.

Deliverables

ingest_source

extract_primitives

DocumentManifest

ExtractedPage

asset extraction

fixture PDFs and extraction golden tests

Dependencies

Phase 1

Agent-independent work

ingest stage

extract stage

raw asset writer

extraction tests

Acceptance criteria

fixture PDFs ingest and extract without manual intervention

per-page raw artifacts produced with bbox/span data

Phase 3 — Canonical IR normalization and asset/symbol resolution

Objective
Convert raw PDF primitives into stable semantic page records.

Deliverables

PageRecord, Block, InlineNode

normalize stage

ID/fingerprint strategy

symbol pack resolver

asset anchor logic

patch set mechanism

hybrid/facsimile fallback support

Dependencies

Phase 2

Agent-independent work

block normalization

symbol detection

patch application

table/figure fallback logic

Acceptance criteria

representative fixture pages normalize into correct block shapes

stable IDs/fingerprints established

unresolved symbols produce explicit issues, not silent drift

Phase 4 — Translation subsystem
Objective
Add bounded structured translation.

Deliverables

TranslationUnit

planner

translation memory

placeholder freezer/restorer

LlmGateway

Gemini provider

validation logic

retry/fallback logic

Dependencies

Phase 3

Agent-independent work

planner

provider adapter

validator

cache layer

benchmark harness

Acceptance criteria

fixture corpus translates successfully with structured outputs

zero placeholder corruption on fixtures

exact cache hits bypass LLM calls

Phase 5 — Localization merge, glossary linking, navigation, search documents

Objective
Turn translations into localized IR and content metadata.

Deliverables

localized page merger

glossary annotation pipeline

navigation tree builder

SearchDocument generator

doc landing metadata

Dependencies

Phase 4

Agent-independent work

glossary linker

navigation builder

search doc exporter

Acceptance criteria

sample bundle contains localized pages, glossary links, and navigation

search documents map to correct page anchors

Phase 6 — QA engine and safe autofix

Objective
Make quality measurable and release-gated.

Deliverables

QAIssue

rule engine

severity aggregation

baseline delta

report generators

safe autofix stage

patch suggestion artifacts

Dependencies

Phase 5

Agent-independent work

rule modules

report rendering

delta logic

fix suggestion format

Acceptance criteria

JSON QA outputs are canonical

failing fixtures fail CI

safe fixes are idempotent

Phase 7 — Reader application

Objective
Build the deployable static reader on top of the bundle.

Deliverables

Next routes

app shell

page renderer

TOC/sidebar

glossary drawer/page

theme/dark mode

route-level error boundaries

Dependencies

Phase 5

Agent-independent work

route generation

block renderer

component library

theme system

Acceptance criteria

sample documents render as static routes

no markdown parser in render path

no runtime content repair logic required

Phase 8 — Search, visual regression, deployment

Objective
Finish production shaping.

Deliverables

Pagefind integration

Playwright e2e

screenshot baselines

preview deploy

production deploy workflow

release manifest

Dependencies

Phase 7

Agent-independent work

search dialog

index build

Playwright tests

GitHub Actions

deployment scripts

Acceptance criteria

search works across doc and section anchors

visual tests pass in CI

preview deploy available from CI

Phase 9 — Multi-document hardening

Objective
Prove the architecture is truly multi-doc.

Deliverables

second document config

catalog landing

doc filters in search

baseline management per doc

shared symbol/glossary reuse across docs

Dependencies

Phase 8

Agent-independent work

catalog UI

cross-doc search filters

multi-doc build orchestration

Acceptance criteria

two documents build in one run

search can filter by doc

no code changes required to add a third document beyond config/packs/patches

15. Risks, Trade-offs, and Rejected Alternatives
Why I chose this architecture

Because this product is really a document compiler plus static reader, not a generic app or a generic translation pipeline.

The main quality risks come from:

ambiguous structure

drifting contracts

overuse of free-form model output

frontend repair logic

poor reproducibility

This design attacks those directly.

Trade-offs
Trade-off 1: No primary database

Chosen: filesystem artifacts
Trade-off: easier to inspect and version, less convenient for ad hoc queries

This is right for v1. A derived SQLite inspector can be added later.

Trade-off 2: Next.js static reader instead of a simpler SPA

Chosen: Next static export
Trade-off: more framework weight than a bare SPA, but much better route structure, static pre-rendering, and code splitting

Worth it.

Trade-off 3: Custom stage runner instead of orchestration platform

Chosen: custom runner
Trade-off: you write a little orchestration code, but you avoid heavy platform complexity

Absolutely correct for this scale.

Trade-off 4: Manual patch layer exists

Chosen: yes
Trade-off: you accept a deliberate escape hatch instead of pretending full automation solves every page

This is practical, not a weakness.

Trade-off 5: LLMs tightly bounded

Chosen: translate text only
Trade-off: less “magic,” more implementation work in deterministic normalization/rendering

That is exactly the right trade.

Rejected alternatives
Rejected: markdown-first canonical pipeline

Reason:

too lossy

too string-fragile

too easy to break lists/headings/callouts/symbols

Rejected: frontend regex repair

Reason:

wrong layer

untestable drift

performance tax

makes static rendering less trustworthy

Rejected: using the LLM to translate entire pages and preserve formatting

Reason:

structurally brittle

hard to validate

hard to diff

high hallucination risk

Rejected: microservices

Reason:

unnecessary operational cost

no benefit for a solo builder

worsens ambiguity

Rejected: Airflow/Prefect/Dagster as the default architecture

Reason:

overkill

more ops than product value

the artifact model matters more than scheduling

Rejected: database as the primary source of truth

Reason:

reduces inspectability

raises migration complexity

not needed for v1

Rejected: search backend service (Algolia/Meilisearch/Elasticsearch)

Reason:

static site does not need it

Pagefind fits much better

What can be postponed

Safe to postpone beyond v1:

OCR fallback for scanned PDFs

automated morphology generation for Russian glossary variants

human review web UI

multi-locale site switching

provider-agnostic LLM benchmark dashboard

derived SQLite inspection DB

collaborative editing/admin tools

What I would absolutely not overengineer in v1

Do not build:

a CMS

a review dashboard web app

a generalized workflow platform

a DB-centric artifact store

a generic multi-provider LLM framework with ten adapters

real-time sync or collaboration

an overly rich IR with dozens of obscure node types

Keep the IR small and sharp. Keep the pipeline explicit. Keep the reader thin.
16. Final Recommended Blueprint
Single recommended architecture in concise form

Build a Python content compiler that ingests each English PDF into a typed block-preserving IR, resolves assets and symbols deterministically, translates only text inline nodes through a schema-constrained LLM layer, runs JSON-first QA, and exports a site bundle. Build a Next.js static reader that consumes the site bundle, renders semantic pages, and adds lazy-loaded Pagefind search, glossary UX, and theme/accessibility features. Store everything as immutable run artifacts with content hashes, stage manifests, and baseline diffs.

Final recommended tech stack

Backend: Python 3.12

Contracts: Pydantic v2 + generated JSON Schema

CLI/orchestration: Typer + custom stage runner

Serialization: orjson

PDF extraction: PyMuPDF

LLM provider: Google Gen AI Python SDK behind internal LlmGateway

Caching: content-addressed filesystem cache

Search: Pagefind

Frontend: Next.js App Router + React + TypeScript + CSS Modules

Frontend state: Server Components + React context/reducer

Backend tests: pytest + mypy + ruff

Frontend tests: Vitest + React Testing Library

E2E/visual: Playwright

CI: GitHub Actions

Deploy: Cloudflare Pages

Observability: structlog + OpenTelemetry + Sentry

Final recommended repo structure
apps/reader
packages/pipeline
packages/contracts
configs/{documents,model-profiles,rule-profiles,symbol-packs,glossary-packs,overrides}
prompts/
tests/{fixtures,backend,frontend,e2e,visual}
artifacts/{cache,runs,releases,state}
docs/{adr,architecture,operator-guides}
Top 10 engineering decisions to lock in before implementation starts

Markdown is not a canonical artifact.

Pydantic models are the source of truth for all stage contracts.

The canonical IR is page-sharded, semantic, and block-preserving.

LLMs only translate text-bearing inline nodes.

All QA is JSON-first; markdown/html reports are derived.

Document config, glossary, symbol pack, and rule profile each have one canonical location.

Runs are immutable and resumable; caches are content-addressed.

Frontend renders validated bundle data and performs no content repair.

Search is static and built with Pagefind, not a search backend.

A deterministic patch/override layer is part of the architecture, not a hack.

A. Spec-kit decomposition

Below is the implementation split I would hand to coding agents.

Epic 001 — Workspace bootstrap

Tasks

root repo files

Python package scaffold

Next app scaffold

uv + pnpm setup

root Makefile

lint/typecheck configs

Outputs

buildable empty monorepo

Epic 002 — Contracts and schema generation

Tasks

define ArtifactEnvelope

define DocumentConfig, PipelineConfig, DocumentManifest

define PageRecord, Block, Asset, Symbol, GlossaryTerm

define QAIssue, Provenance, BuildArtifact, SearchDocument

generate JSON Schema and TS types

Outputs

canonical models package

generated contracts package

Epic 003 — Config system

Tasks

YAML loaders and validators

document catalog loader

model/rule/symbol/glossary/override profile loaders

config hash calculator

Outputs

ResolvedRunPlan

Epic 004 — Artifact runtime and stage registry

Tasks

run directory creator

artifact writers/readers

stage manifest format

cache key builder

resume logic

inspect CLI command

Outputs

runnable stage framework
Epic 005 — PDF ingest

Tasks

source hashing

PDF metadata extraction

outline extraction

page dimension extraction

DocumentManifest writer

Outputs

ingest_source stage

Epic 006 — Primitive extraction

Tasks

per-page PyMuPDF extraction

raw page JSON writer

asset extraction

vector metadata capture

extraction tests

Outputs

extract_primitives stage

Epic 007 — Canonical IR normalization

Tasks

reading order logic

block segmentation

heading/list/callout/caption/table detection

stable ID/fingerprint generation

page/block provenance mapping

Outputs

normalize_layout stage

PageRecord fixtures

Epic 008 — Asset and symbol resolution

Tasks

asset derivative builder

symbol pack matcher

figure-caption pairing

asset anchor assignment

unresolved symbol issue generation

Outputs

resolve_assets_symbols stage

Epic 009 — Translation subsystem

Tasks

translation unit planner

glossary placeholder freezer

translation memory lookup

LlmGateway

Gemini provider

structured-output validator

retry/fallback logic

Outputs

plan_translation + translate_units

Epic 010 — Localization merge and content enrichment

Tasks

merge translations back into IR

glossary hit annotation

section path finalization

navigation builder

search document builder

Outputs

localized page artifacts

navigation + search docs

Epic 011 — QA engine

Tasks

QAIssue engine

initial ruleset

summary aggregation

baseline delta comparison

markdown/html derived reports

Outputs

evaluate_qa

Epic 012 — Safe autofix and patch suggestions (planned, not implemented)

Tasks

patch schema

safe deterministic fixers

issue-linked patch suggestions

audit log

Outputs

apply_safe_fixes (planned)

Epic 013 — Site bundle export

Tasks

export doc/page/glossary/nav JSON

export asset map/sprite

export catalog manifest

build artifact manifest

Outputs

export_site_bundle

Epic 014 — Reader application

Tasks

route tree

app shell

page renderer

block/inline renderers

sidebar/TOC

glossary drawer/page

theme system

error boundaries

Outputs

functional static reader

Epic 015 — Search integration

Tasks

add Pagefind metadata/filter/weight attrs

lazy search dialog

doc filter support

search result navigation to anchors

Outputs

site search

Epic 016 — Test harness

Tasks

fixture corpus

backend golden tests

mocked LLM tests

frontend component tests

Playwright e2e

screenshot baselines

Outputs

CI-grade validation suite

Epic 017 — CI/CD

Tasks

GitHub Actions workflows

preview deploy

release workflow

artifact upload for failed runs

baseline snapshot storage

Outputs

automated delivery pipeline
B. Starter repo skeleton
Initial folder/file skeleton
/
├─ Makefile
├─ README.md
├─ pyproject.toml
├─ package.json
├─ pnpm-workspace.yaml
├─ .gitignore
├─ .editorconfig
│
├─ docs/
│  └─ adr/
│     ├─ 0001-canonical-ir.md
│     ├─ 0002-no-markdown-canonical.md
│     ├─ 0003-static-reader-bundle.md
│     └─ 0004-llm-translation-boundary.md
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
│  └─ translate/
│     └─ v1/
│        ├─ system.j2
│        ├─ response_schema.json
│        └─ examples.json
│
├─ packages/
│  ├─ pipeline/
│  │  ├─ pyproject.toml
│  │  └─ src/aeon_reader_pipeline/
│  │     ├─ __init__.py
│  │     ├─ cli/
│  │     │  └─ main.py
│  │     ├─ config/
│  │     │  ├─ loader.py
│  │     │  └─ hashing.py
│  │     ├─ models/
│  │     │  ├─ base.py
│  │     │  ├─ config_models.py
│  │     │  ├─ manifest_models.py
│  │     │  ├─ ir_models.py
│  │     │  ├─ qa_models.py
│  │     │  └─ build_models.py
│  │     ├─ io/
│  │     │  ├─ json_io.py
│  │     │  └─ artifact_store.py
│  │     ├─ cache/
│  │     │  └─ keys.py
│  │     ├─ llm/
│  │     │  ├─ base.py
│  │     │  ├─ gemini.py
│  │     │  ├─ prompts.py
│  │     │  └─ validation.py
│  │     ├─ stages/
│  │     │  ├─ resolve_run.py
│  │     │  ├─ ingest_source.py
│  │     │  ├─ extract_primitives.py
│  │     │  ├─ collect_evidence.py
│  │     │  ├─ resolve_page_ir.py
│  │     │  ├─ normalize_layout.py
│  │     │  ├─ resolve_assets_symbols.py
│  │     │  ├─ plan_translation.py
│  │     │  ├─ translate_units.py
│  │     │  ├─ merge_localization.py
│  │     │  ├─ enrich_content.py
│  │     │  ├─ evaluate_qa.py
│  │     │  ├─ confidence.py
│  │     │  ├─ export_site_bundle.py
│  │     │  ├─ build_reader.py
│  │     │  ├─ index_search.py
│  │     │  └─ package_release.py
│  │     ├─ qa/
│  │     │  ├─ rules/
│  │     │  ├─ engine.py
│  │     │  └─ reports.py
│  │     └─ migrations/
│  │
│  └─ contracts/
│     ├─ jsonschema/.gitkeep
│     └─ typescript/.gitkeep
│
├─ apps/
│  └─ reader/
│     ├─ package.json
│     ├─ next.config.ts
│     ├─ tsconfig.json
│     ├─ app/
│     │  ├─ layout.tsx
│     │  ├─ page.tsx
│     │  └─ docs/
│     │     └─ [docId]/
│     │        ├─ page.tsx
│     │        ├─ glossary/page.tsx
│     │        └─ page/[pageNo]/page.tsx
│     ├─ components/
│     │  ├─ AppShell.tsx
│     │  ├─ BlockRenderer.tsx
│     │  ├─ InlineRenderer.tsx
│     │  ├─ DocSidebar.tsx
│     │  ├─ SearchDialog.tsx
│     │  └─ ErrorBoundary.tsx
│     ├─ lib/
│     │  ├─ bundle.ts
│     │  ├─ routes.ts
│     │  └─ types.ts
│     ├─ styles/
│     │  └─ theme.css
│     └─ generated/.gitkeep
│
├─ tests/
│  ├─ fixtures/
│  │  ├─ pdf/
│  │  └─ site-bundles/
│  ├─ backend/
│  ├─ frontend/
│  ├─ e2e/
│  └─ visual/
│
└─ artifacts/
   ├─ .gitkeep
   ├─ cache/
   ├─ runs/
   ├─ releases/
   └─ state/
First files I would create, in order
docs/adr/0001-canonical-ir.md
Lock the decision that markdown is not canonical.

packages/pipeline/src/aeon_reader_pipeline/models/base.py
Base artifact envelope + provenance.

packages/pipeline/src/aeon_reader_pipeline/models/config_models.py
DocumentConfig, PipelineConfig.

packages/pipeline/src/aeon_reader_pipeline/models/ir_models.py
PageRecord, Block, InlineNode, Asset.

packages/pipeline/src/aeon_reader_pipeline/models/qa_models.py
QAIssue, IssueLocation.

packages/pipeline/src/aeon_reader_pipeline/config/loader.py
YAML loaders + validation.

packages/pipeline/src/aeon_reader_pipeline/io/artifact_store.py
run dir creation, read/write helpers.

packages/pipeline/src/aeon_reader_pipeline/stages/resolve_run.py
first real stage.

packages/pipeline/src/aeon_reader_pipeline/stages/ingest_source.py
source hash + manifest.

packages/pipeline/src/aeon_reader_pipeline/stages/extract_primitives.py
first content stage.

packages/pipeline/src/aeon_reader_pipeline/cli/main.py
stable operator interface.

apps/reader/app/docs/[docId]/page/[pageNo]/page.tsx
first typed page route.

apps/reader/components/BlockRenderer.tsx
deterministic renderer switch.

configs/documents/aeon-trespass-core.yaml
first real document declaration.

tests/fixtures/pdf/<small-fixture>.pdf
start the golden corpus immediately.

