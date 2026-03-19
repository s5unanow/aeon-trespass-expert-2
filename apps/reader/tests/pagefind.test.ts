import { describe, expect, it, vi, beforeEach } from "vitest";

// Each test gets a fresh module to avoid shared pagefindInstance state
beforeEach(() => {
  vi.resetModules();
});

describe("getPagefind", () => {
  it("returns null when pagefind is not available", async () => {
    vi.doMock("/pagefind/pagefind.js", () => {
      throw new Error("Module not found");
    });
    const { getPagefind } = await import("@/lib/pagefind");
    const result = await getPagefind();
    expect(result).toBeNull();
  });

  // Note: the success path (pagefind instance available) cannot be unit-tested
  // here because the module uses a runtime dynamic import() with a string variable,
  // which Vitest cannot intercept via vi.doMock. The success path is covered by
  // Playwright smoke tests against a real built site.
});

describe("search", () => {
  it("returns empty array for blank query", async () => {
    const { search } = await import("@/lib/pagefind");
    const result = await search("   ");
    expect(result).toEqual([]);
  });

  it("returns empty array for empty string", async () => {
    const { search } = await import("@/lib/pagefind");
    const result = await search("");
    expect(result).toEqual([]);
  });

  it("returns empty array when pagefind is unavailable", async () => {
    const { search } = await import("@/lib/pagefind");
    // Since pagefind.js doesn't exist in test env, getPagefind returns null
    const result = await search("titan");
    expect(result).toEqual([]);
  });
});
