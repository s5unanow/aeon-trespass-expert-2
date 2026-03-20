import { mkdirSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { describe, expect, it, beforeAll, afterAll, vi, beforeEach } from "vitest";
import type { SiteBundleManifest, CatalogManifest } from "@aeon-reader/contracts";

const FIXTURE_DIR = join(__dirname, "__fixtures_seo__");
const GENERATED_DIR = join(FIXTURE_DIR, "generated");

const sampleManifest: SiteBundleManifest = {
  doc_id: "core-rulebook",
  run_id: "run-001",
  page_count: 3,
  title_en: "Core Rulebook",
  title_ru: "Основная книга правил",
  route_base: "/docs/core-rulebook",
  source_locale: "en",
  target_locale: "ru",
  translation_coverage: 0.85,
  has_navigation: true,
  has_search: false,
  has_glossary: true,
  assets: [],
  qa_accepted: true,
  is_preview: false,
  filtered_pages: null,
  total_source_pages: null,
  stage_version: "1.0.0",
};

const sampleCatalog: CatalogManifest = {
  documents: [
    {
      doc_id: "core-rulebook",
      slug: "core-rulebook",
      title_en: "Core Rulebook",
      title_ru: "Основная книга правил",
      route_base: "/docs/core-rulebook",
      page_count: 3,
      translation_coverage: 0.85,
    },
  ],
  total_documents: 1,
};

beforeAll(() => {
  const docDir = join(GENERATED_DIR, "core-rulebook");
  const pagesDir = join(docDir, "pages");
  mkdirSync(pagesDir, { recursive: true });
  writeFileSync(join(docDir, "bundle_manifest.json"), JSON.stringify(sampleManifest));
  writeFileSync(join(GENERATED_DIR, "catalog.json"), JSON.stringify(sampleCatalog));
  for (let p = 1; p <= 3; p++) {
    writeFileSync(
      join(pagesDir, `p${String(p).padStart(4, "0")}.json`),
      JSON.stringify({ page_number: p, doc_id: "core-rulebook", blocks: [], anchors: [] }),
    );
  }
});

afterAll(() => {
  rmSync(FIXTURE_DIR, { recursive: true, force: true });
});

beforeEach(() => {
  vi.resetModules();
  vi.spyOn(process, "cwd").mockReturnValue(FIXTURE_DIR);
});

describe("seo constants", () => {
  it("exports SITE_URL, SITE_NAME, and SITE_DESCRIPTION", async () => {
    const { SITE_URL, SITE_NAME, SITE_DESCRIPTION } = await import("@/lib/seo");
    expect(SITE_URL).toMatch(/^https?:\/\//);
    expect(SITE_NAME).toBe("Aeon Trespass Reader");
    expect(SITE_DESCRIPTION).toContain("Aeon Trespass");
  });

  it("sharedMetadata includes OG and Twitter defaults", async () => {
    const { sharedMetadata } = await import("@/lib/seo");
    expect(sharedMetadata.openGraph).toBeDefined();
    expect(sharedMetadata.twitter).toBeDefined();
    expect(sharedMetadata.metadataBase).toBeInstanceOf(URL);
  });
});

describe("robots", () => {
  it("allows all user agents and includes sitemap", async () => {
    const { default: robots } = await import("@/app/robots");
    const result = robots();
    expect(result.rules).toEqual({ userAgent: "*", allow: "/" });
    expect(result.sitemap).toContain("/sitemap.xml");
  });
});

describe("sitemap", () => {
  it("generates entries for catalog, documents, pages, and glossary", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = sitemap();

    // Catalog landing + 1 doc landing + 3 pages + 1 glossary = 6
    expect(entries).toHaveLength(6);

    const urls = entries.map((e) => e.url);
    expect(urls[0]).toMatch(/\/$/); // catalog
    expect(urls[1]).toContain("/docs/core-rulebook/");
    expect(urls[2]).toContain("/docs/core-rulebook/page/1/");
    expect(urls[3]).toContain("/docs/core-rulebook/page/2/");
    expect(urls[4]).toContain("/docs/core-rulebook/page/3/");
    expect(urls[5]).toContain("/docs/core-rulebook/glossary/");
  });

  it("uses absolute URLs", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = sitemap();
    for (const entry of entries) {
      expect(entry.url).toMatch(/^https?:\/\//);
    }
  });

  it("assigns priority values", async () => {
    const { default: sitemap } = await import("@/app/sitemap");
    const entries = sitemap();
    expect(entries[0].priority).toBe(1.0); // catalog
    expect(entries[1].priority).toBe(0.9); // doc landing
    expect(entries[2].priority).toBe(0.7); // page
    expect(entries[5].priority).toBe(0.5); // glossary
  });
});
