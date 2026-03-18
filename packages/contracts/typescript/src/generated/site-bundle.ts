/**
 * Public site bundle contracts — generated from Python models.
 *
 * These types mirror the Pydantic models in:
 *   packages/pipeline/src/aeon_reader_pipeline/models/site_bundle_models.py
 *
 * Do NOT edit manually — regenerate with `make schemas`.
 */

// ---------------------------------------------------------------------------
// Inline node types
// ---------------------------------------------------------------------------

export interface BundleTextRun {
  kind: "text";
  text: string;
  ru_text: string | null;
  bold: boolean;
  italic: boolean;
  monospace: boolean;
}

export interface BundleSymbolRef {
  kind: "symbol";
  symbol_id: string;
  alt_text: string;
}

export interface BundleGlossaryRef {
  kind: "glossary_ref";
  term_id: string;
  surface_form: string;
  ru_surface_form: string;
}

export type BundleInlineNode = BundleTextRun | BundleSymbolRef | BundleGlossaryRef;

// ---------------------------------------------------------------------------
// Block types
// ---------------------------------------------------------------------------

export interface BundleHeadingBlock {
  kind: "heading";
  block_id: string;
  level: number;
  content: BundleInlineNode[];
  anchor: string;
}

export interface BundleParagraphBlock {
  kind: "paragraph";
  block_id: string;
  content: BundleInlineNode[];
}

export interface BundleListItemBlock {
  kind: "list_item";
  block_id: string;
  bullet: string;
  content: BundleInlineNode[];
}

export interface BundleListBlock {
  kind: "list";
  block_id: string;
  list_type: "unordered" | "ordered";
  items: BundleListItemBlock[];
}

export interface BundleFigureBlock {
  kind: "figure";
  block_id: string;
  asset_ref: string;
  alt_text: string;
  caption_block_id: string | null;
}

export interface BundleCaptionBlock {
  kind: "caption";
  block_id: string;
  content: BundleInlineNode[];
  parent_block_id: string | null;
}

export interface BundleTableBlock {
  kind: "table";
  block_id: string;
  rows: number;
  cols: number;
}

export interface BundleCalloutBlock {
  kind: "callout";
  block_id: string;
  callout_type: string;
  content: BundleInlineNode[];
}

export interface BundleDividerBlock {
  kind: "divider";
  block_id: string;
}

export type BundleBlock =
  | BundleHeadingBlock
  | BundleParagraphBlock
  | BundleListBlock
  | BundleListItemBlock
  | BundleFigureBlock
  | BundleCaptionBlock
  | BundleTableBlock
  | BundleCalloutBlock
  | BundleDividerBlock;

// ---------------------------------------------------------------------------
// Page-level types
// ---------------------------------------------------------------------------

export interface BundlePageAnchor {
  anchor_id: string;
  block_id: string;
  label: string;
}

export interface BundlePage {
  page_number: number;
  doc_id: string;
  width_pt: number;
  height_pt: number;
  render_mode: "semantic" | "hybrid" | "facsimile";
  blocks: BundleBlock[];
  anchors: BundlePageAnchor[];
}

// ---------------------------------------------------------------------------
// Bundle manifests
// ---------------------------------------------------------------------------

export interface BundleAssetEntry {
  asset_ref: string;
  path: string;
  content_type: string;
  size_bytes: number;
}

export interface SiteBundleManifest {
  doc_id: string;
  run_id: string;
  page_count: number;
  title_en: string;
  title_ru: string;
  route_base: string;
  source_locale: string;
  target_locale: string;
  translation_coverage: number;
  has_navigation: boolean;
  has_search: boolean;
  has_glossary: boolean;
  assets: BundleAssetEntry[];
  qa_accepted: boolean;
  stage_version: string;
}

// ---------------------------------------------------------------------------
// Glossary
// ---------------------------------------------------------------------------

export interface BundleGlossaryEntry {
  term_id: string;
  en_canonical: string;
  ru_preferred: string;
  definition_ru: string;
  definition_en: string | null;
}

export interface BundleGlossary {
  doc_id: string;
  entries: BundleGlossaryEntry[];
  total_entries: number;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export interface NavEntry {
  anchor_id: string;
  block_id: string;
  label_en: string;
  label_ru: string;
  level: number;
  page_number: number;
  children: NavEntry[];
}

export interface NavigationTree {
  doc_id: string;
  entries: NavEntry[];
  total_entries: number;
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export interface CatalogEntry {
  doc_id: string;
  slug: string;
  title_en: string;
  title_ru: string;
  route_base: string;
  page_count: number;
  translation_coverage: number;
}

export interface CatalogManifest {
  documents: CatalogEntry[];
  total_documents: number;
}
