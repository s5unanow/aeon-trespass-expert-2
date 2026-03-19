/**
 * Bundle loaders — read generated site bundle data at build time.
 *
 * These loaders read from apps/reader/generated/<docId>/ and return
 * typed contract objects. They run server-side only (Next.js Server Components).
 */

import { readFileSync, readdirSync, existsSync } from "fs";
import { join } from "path";
import type {
  BundleGlossary,
  BundlePage,
  CatalogManifest,
  NavigationTree,
  SiteBundleManifest,
} from "@aeon-reader/contracts";

const GENERATED_ROOT = join(process.cwd(), "generated");

function readJson<T>(path: string): T {
  const raw = readFileSync(path, "utf-8");
  return JSON.parse(raw) as T;
}

/**
 * List all document IDs available in the generated directory.
 */
export function listDocIds(): string[] {
  if (!existsSync(GENERATED_ROOT)) return [];
  return readdirSync(GENERATED_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

/**
 * Load the site bundle manifest for a document.
 */
export function loadBundleManifest(docId: string): SiteBundleManifest {
  const path = join(GENERATED_ROOT, docId, "bundle_manifest.json");
  return readJson<SiteBundleManifest>(path);
}

/**
 * Load a single bundle page.
 */
export function loadBundlePage(docId: string, pageNo: number): BundlePage {
  const filename = `p${String(pageNo).padStart(4, "0")}.json`;
  const path = join(GENERATED_ROOT, docId, "pages", filename);
  return readJson<BundlePage>(path);
}

/**
 * Load the navigation tree for a document.
 */
export function loadNavigation(docId: string): NavigationTree | null {
  const path = join(GENERATED_ROOT, docId, "navigation.json");
  if (!existsSync(path)) return null;
  return readJson<NavigationTree>(path);
}

/**
 * Load glossary entries for a document.
 */
export function loadGlossary(docId: string): BundleGlossary | null {
  const path = join(GENERATED_ROOT, docId, "glossary.json");
  if (!existsSync(path)) return null;
  return readJson<BundleGlossary>(path);
}

/**
 * Load the authoritative catalog manifest.
 *
 * Uses catalog.json written by the pipeline's build_reader stage.
 * Falls back to directory scanning if catalog.json is missing.
 */
export function loadCatalog(): CatalogManifest {
  const catalogPath = join(GENERATED_ROOT, "catalog.json");
  if (existsSync(catalogPath)) {
    return readJson<CatalogManifest>(catalogPath);
  }
  // Fallback: scan directories (for backwards compatibility)
  const docIds = listDocIds();
  const documents = docIds.map((docId) => {
    const manifest = loadBundleManifest(docId);
    return {
      doc_id: manifest.doc_id,
      slug: manifest.doc_id,
      title_en: manifest.title_en,
      title_ru: manifest.title_ru,
      route_base: manifest.route_base,
      page_count: manifest.page_count,
      translation_coverage: manifest.translation_coverage,
    };
  });
  return { documents, total_documents: documents.length };
}

/**
 * Check if a document exists in the generated directory.
 */
export function docExists(docId: string): boolean {
  return existsSync(join(GENERATED_ROOT, docId, "bundle_manifest.json"));
}

/**
 * Check if a page exists for a given document.
 */
export function pageExists(docId: string, pageNo: number): boolean {
  const filename = `p${String(pageNo).padStart(4, "0")}.json`;
  return existsSync(join(GENERATED_ROOT, docId, "pages", filename));
}
