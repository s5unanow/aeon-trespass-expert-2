import { describe, expect, it } from "vitest";
import {
  catalogRoute,
  docRoute,
  pageRoute,
  glossaryRoute,
  parseDocParams,
  parsePageParams,
} from "@/lib/routes";

describe("route helpers", () => {
  it("catalogRoute returns root path", () => {
    expect(catalogRoute()).toBe("/");
  });

  it("docRoute returns document path with trailing slash", () => {
    expect(docRoute("core-rulebook")).toBe("/docs/core-rulebook/");
  });

  it("pageRoute returns page path with trailing slash", () => {
    expect(pageRoute("core-rulebook", 1)).toBe("/docs/core-rulebook/page/1/");
    expect(pageRoute("core-rulebook", 42)).toBe("/docs/core-rulebook/page/42/");
  });

  it("glossaryRoute returns glossary path with trailing slash", () => {
    expect(glossaryRoute("core-rulebook")).toBe("/docs/core-rulebook/glossary/");
  });
});

describe("param parsers", () => {
  it("parseDocParams extracts docId", () => {
    expect(parseDocParams({ docId: "core-rulebook" })).toEqual({
      docId: "core-rulebook",
    });
  });

  it("parsePageParams extracts docId and parses pageNo as integer", () => {
    expect(parsePageParams({ docId: "core-rulebook", pageNo: "5" })).toEqual({
      docId: "core-rulebook",
      pageNo: 5,
    });
  });

  it("parsePageParams handles string '0'", () => {
    expect(parsePageParams({ docId: "core", pageNo: "0" })).toEqual({
      docId: "core",
      pageNo: 0,
    });
  });

  it("parsePageParams returns NaN for non-numeric input", () => {
    const result = parsePageParams({ docId: "core", pageNo: "abc" });
    expect(result.docId).toBe("core");
    expect(isNaN(result.pageNo)).toBe(true);
  });
});
