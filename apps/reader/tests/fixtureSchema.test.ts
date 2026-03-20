/**
 * Validate committed site-bundle fixtures against checked-in JSON Schema.
 *
 * This test proves that the fixture data consumed by the reader's bundle
 * loaders satisfies the public contract, even though the loaders themselves
 * use `JSON.parse(raw) as T` (type assertion without runtime validation).
 *
 * Runs without network access as part of contract verification.
 */

import { readFileSync, readdirSync, existsSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";
import Ajv from "ajv";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const SCHEMA_DIR = join(REPO_ROOT, "packages", "contracts", "jsonschema");
const FIXTURE_ROOT = join(REPO_ROOT, "tests", "fixtures", "site-bundles");

function loadJson(path: string): unknown {
  return JSON.parse(readFileSync(path, "utf-8"));
}

function loadSchema(name: string): object {
  const path = join(SCHEMA_DIR, `${name}.json`);
  return loadJson(path) as object;
}

/**
 * Create an Ajv validator for a schema that may contain internal $defs/$ref.
 * JSON Schema Draft 2020-12 / Draft 7 style self-contained schemas.
 */
function createValidator(schemaName: string) {
  const schema = loadSchema(schemaName);
  const ajv = new Ajv({ allErrors: true, strict: false });
  return ajv.compile(schema);
}

/** Discover document fixture directories. */
function discoverDocDirs(): string[] {
  return readdirSync(FIXTURE_ROOT, { withFileTypes: true })
    .filter(
      (d) =>
        d.isDirectory() &&
        existsSync(join(FIXTURE_ROOT, d.name, "bundle_manifest.json")),
    )
    .map((d) => d.name)
    .sort();
}

/** Discover page files under a document directory. */
function discoverPages(docId: string): string[] {
  const pagesDir = join(FIXTURE_ROOT, docId, "pages");
  if (!existsSync(pagesDir)) return [];
  return readdirSync(pagesDir)
    .filter((f) => f.startsWith("p") && f.endsWith(".json"))
    .sort();
}

const docIds = discoverDocDirs();

describe("fixture bundle_manifest.json validates against SiteBundleManifest schema", () => {
  const validate = createValidator("SiteBundleManifest");

  it.each(docIds)("%s/bundle_manifest.json", (docId) => {
    const data = loadJson(join(FIXTURE_ROOT, docId, "bundle_manifest.json"));
    const valid = validate(data);
    expect(valid, JSON.stringify(validate.errors, null, 2)).toBe(true);
  });
});

describe("fixture pages validate against BundlePage schema", () => {
  const validate = createValidator("BundlePage");

  const pageParams: Array<{ docId: string; page: string }> = [];
  for (const docId of docIds) {
    for (const page of discoverPages(docId)) {
      pageParams.push({ docId, page });
    }
  }

  it.each(pageParams)("$docId/pages/$page", ({ docId, page }) => {
    const data = loadJson(join(FIXTURE_ROOT, docId, "pages", page));
    const valid = validate(data);
    expect(valid, JSON.stringify(validate.errors, null, 2)).toBe(true);
  });
});

describe("fixture navigation.json validates against NavigationTree schema", () => {
  const validate = createValidator("NavigationTree");

  const docsWithNav = docIds.filter((id) =>
    existsSync(join(FIXTURE_ROOT, id, "navigation.json")),
  );

  it.each(docsWithNav)("%s/navigation.json", (docId) => {
    const data = loadJson(join(FIXTURE_ROOT, docId, "navigation.json"));
    const valid = validate(data);
    expect(valid, JSON.stringify(validate.errors, null, 2)).toBe(true);
  });
});

describe("fixture catalog.json validates against CatalogManifest schema", () => {
  const validate = createValidator("CatalogManifest");

  it("catalog.json", () => {
    const catalogPath = join(FIXTURE_ROOT, "catalog.json");
    expect(existsSync(catalogPath)).toBe(true);
    const data = loadJson(catalogPath);
    const valid = validate(data);
    expect(valid, JSON.stringify(validate.errors, null, 2)).toBe(true);
  });
});

describe("schema gate catches invalid payloads", () => {
  it("rejects manifest missing run_id", () => {
    const validate = createValidator("SiteBundleManifest");
    const invalid = { doc_id: "x", page_count: 1, title_en: "X" };
    expect(validate(invalid)).toBe(false);
    const fields = validate.errors?.map((e) => e.params?.missingProperty);
    expect(fields).toContain("run_id");
  });

  it("rejects page with invalid render_mode", () => {
    const validate = createValidator("BundlePage");
    const invalid = {
      page_number: 1,
      doc_id: "x",
      width_pt: 595,
      height_pt: 842,
      render_mode: "invalid",
    };
    expect(validate(invalid)).toBe(false);
  });

  it("rejects catalog entry missing slug", () => {
    const validate = createValidator("CatalogManifest");
    const invalid = {
      documents: [{ doc_id: "x", title_en: "X" }],
    };
    expect(validate(invalid)).toBe(false);
  });
});
