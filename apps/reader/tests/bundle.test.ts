import { mkdirSync, writeFileSync, rmSync, unlinkSync, existsSync } from "fs";
import { join } from "path";
import { describe, expect, it, beforeAll, afterAll, vi, beforeEach } from "vitest";
import type {
  SiteBundleManifest,
  BundlePage,
  NavigationTree,
  BundleGlossary,
  CatalogManifest,
} from "@aeon-reader/contracts";

// We need to override the GENERATED_ROOT constant in bundle.ts.
// Since it uses process.cwd() at module load time, we mock cwd.
const FIXTURE_DIR = join(__dirname, "__fixtures_bundle__");
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

const samplePage: BundlePage = {
  page_number: 1,
  doc_id: "core-rulebook",
  width_pt: 595,
  height_pt: 842,
  render_mode: "semantic",
  fallback_image_ref: null,
  blocks: [],
  anchors: [],
};

const sampleNavigation: NavigationTree = {
  doc_id: "core-rulebook",
  entries: [
    {
      anchor_id: "ch1",
      block_id: "b1",
      label_en: "Chapter 1",
      label_ru: "Глава 1",
      level: 1,
      page_number: 1,
      children: [],
    },
  ],
  total_entries: 1,
};

const sampleGlossary: BundleGlossary = {
  doc_id: "core-rulebook",
  entries: [
    {
      term_id: "titan",
      en_canonical: "Titan",
      ru_preferred: "Титан",
      definition_ru: "Древнее существо.",
      definition_en: "An ancient being.",
    },
  ],
  total_entries: 1,
};

beforeAll(() => {
  // Create fixture directory structure
  const docDir = join(GENERATED_DIR, "core-rulebook");
  const pagesDir = join(docDir, "pages");
  mkdirSync(pagesDir, { recursive: true });

  writeFileSync(join(docDir, "bundle_manifest.json"), JSON.stringify(sampleManifest));
  writeFileSync(join(pagesDir, "p0001.json"), JSON.stringify(samplePage));
  writeFileSync(join(pagesDir, "p0002.json"), JSON.stringify({ ...samplePage, page_number: 2 }));
  writeFileSync(join(pagesDir, "p0003.json"), JSON.stringify({ ...samplePage, page_number: 3 }));
  writeFileSync(join(docDir, "navigation.json"), JSON.stringify(sampleNavigation));
  writeFileSync(join(docDir, "glossary.json"), JSON.stringify(sampleGlossary));
});

afterAll(() => {
  rmSync(FIXTURE_DIR, { recursive: true, force: true });
});

// Each test re-imports bundle.ts with a fresh cwd mock
beforeEach(() => {
  vi.resetModules();
  vi.spyOn(process, "cwd").mockReturnValue(FIXTURE_DIR);
});

async function loadBundle() {
  return import("@/lib/bundle");
}

describe("listDocIds", () => {
  it("returns document directory names", async () => {
    const { listDocIds } = await loadBundle();
    const ids = listDocIds();
    expect(ids).toEqual(["core-rulebook"]);
  });

  it("returns empty array when generated dir does not exist", async () => {
    vi.spyOn(process, "cwd").mockReturnValue("/nonexistent/path");
    const { listDocIds } = await loadBundle();
    expect(listDocIds()).toEqual([]);
  });
});

describe("loadBundleManifest", () => {
  it("loads and parses manifest JSON", async () => {
    const { loadBundleManifest } = await loadBundle();
    const manifest = loadBundleManifest("core-rulebook");
    expect(manifest.doc_id).toBe("core-rulebook");
    expect(manifest.page_count).toBe(3);
    expect(manifest.title_en).toBe("Core Rulebook");
    expect(manifest.translation_coverage).toBe(0.85);
  });

  it("throws for non-existent document", async () => {
    const { loadBundleManifest } = await loadBundle();
    expect(() => loadBundleManifest("nonexistent")).toThrow();
  });
});

describe("loadBundlePage", () => {
  it("loads page with zero-padded filename", async () => {
    const { loadBundlePage } = await loadBundle();
    const page = loadBundlePage("core-rulebook", 1);
    expect(page.page_number).toBe(1);
    expect(page.doc_id).toBe("core-rulebook");
    expect(page.render_mode).toBe("semantic");
  });

  it("loads page 3", async () => {
    const { loadBundlePage } = await loadBundle();
    const page = loadBundlePage("core-rulebook", 3);
    expect(page.page_number).toBe(3);
  });

  it("throws for non-existent page", async () => {
    const { loadBundlePage } = await loadBundle();
    expect(() => loadBundlePage("core-rulebook", 999)).toThrow();
  });
});

describe("loadNavigation", () => {
  it("loads navigation tree", async () => {
    const { loadNavigation } = await loadBundle();
    const nav = loadNavigation("core-rulebook");
    expect(nav).not.toBeNull();
    expect(nav!.doc_id).toBe("core-rulebook");
    expect(nav!.entries).toHaveLength(1);
    expect(nav!.entries[0].label_en).toBe("Chapter 1");
  });

  it("returns null when navigation file does not exist", async () => {
    const emptyDocDir = join(GENERATED_DIR, "no-nav-doc");
    try {
      mkdirSync(emptyDocDir, { recursive: true });
      writeFileSync(join(emptyDocDir, "bundle_manifest.json"), JSON.stringify(sampleManifest));

      const { loadNavigation } = await loadBundle();
      expect(loadNavigation("no-nav-doc")).toBeNull();
    } finally {
      rmSync(emptyDocDir, { recursive: true, force: true });
    }
  });
});

describe("loadGlossary", () => {
  it("loads glossary entries", async () => {
    const { loadGlossary } = await loadBundle();
    const glossary = loadGlossary("core-rulebook");
    expect(glossary).not.toBeNull();
    expect(glossary!.entries).toHaveLength(1);
    expect(glossary!.entries[0].term_id).toBe("titan");
  });

  it("returns null when glossary file does not exist", async () => {
    const emptyDocDir = join(GENERATED_DIR, "no-glossary-doc");
    try {
      mkdirSync(emptyDocDir, { recursive: true });
      writeFileSync(join(emptyDocDir, "bundle_manifest.json"), JSON.stringify(sampleManifest));

      const { loadGlossary } = await loadBundle();
      expect(loadGlossary("no-glossary-doc")).toBeNull();
    } finally {
      rmSync(emptyDocDir, { recursive: true, force: true });
    }
  });
});

describe("docExists", () => {
  it("returns true for existing document", async () => {
    const { docExists } = await loadBundle();
    expect(docExists("core-rulebook")).toBe(true);
  });

  it("returns false for non-existent document", async () => {
    const { docExists } = await loadBundle();
    expect(docExists("nonexistent")).toBe(false);
  });
});

describe("pageExists", () => {
  it("returns true for existing page", async () => {
    const { pageExists } = await loadBundle();
    expect(pageExists("core-rulebook", 1)).toBe(true);
    expect(pageExists("core-rulebook", 3)).toBe(true);
  });

  it("returns false for non-existent page", async () => {
    const { pageExists } = await loadBundle();
    expect(pageExists("core-rulebook", 999)).toBe(false);
  });

  it("returns false for non-existent document", async () => {
    const { pageExists } = await loadBundle();
    expect(pageExists("nonexistent", 1)).toBe(false);
  });
});

describe("loadCatalog", () => {
  it("loads catalog.json when present", async () => {
    const catalog: CatalogManifest = {
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
    writeFileSync(join(GENERATED_DIR, "catalog.json"), JSON.stringify(catalog));

    const { loadCatalog } = await loadBundle();
    const result = loadCatalog();
    expect(result.total_documents).toBe(1);
    expect(result.documents[0].doc_id).toBe("core-rulebook");

    unlinkSync(join(GENERATED_DIR, "catalog.json"));
  });

  it("falls back to directory scan when catalog.json is missing", async () => {
    const { loadCatalog } = await loadBundle();
    const result = loadCatalog();
    expect(result.total_documents).toBe(1);
    expect(result.documents[0].doc_id).toBe("core-rulebook");
    expect(result.documents[0].page_count).toBe(3);
  });
});
