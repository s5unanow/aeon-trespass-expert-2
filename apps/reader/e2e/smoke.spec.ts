import { test, expect } from "@playwright/test";

test.describe("Catalog page", () => {
  test("loads and shows document list", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".catalog-page")).toBeVisible();
    await expect(page.locator(".catalog-item").first()).toBeVisible();
  });

  test("shows multiple documents in catalog", async ({ page }) => {
    await page.goto("/");
    const items = page.locator(".catalog-item");
    await expect(items).toHaveCount(2);
  });

  test("links to document landing page", async ({ page }) => {
    await page.goto("/");
    const link = page.locator(".catalog-link").first();
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(/\/docs\/aeon-trespass-core\//);
  });
});

test.describe("Document landing page", () => {
  test("shows document title and metadata", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/");
    await expect(page.locator(".doc-landing h1")).toBeVisible();
    await expect(page.locator(".doc-meta")).toBeVisible();
  });

  test("has start reading link", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/");
    const startLink = page.locator(".doc-start-link");
    await expect(startLink).toBeVisible();
    await startLink.click();
    await expect(page).toHaveURL(/\/page\/1\//);
  });
});

test.describe("Reader page", () => {
  test("renders page content with sidebar", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/page/3/");
    await expect(page.locator(".doc-sidebar")).toBeVisible();
    await expect(page.locator(".doc-content")).toBeVisible();
  });

  test("sidebar has table of contents", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/page/3/");
    const nav = page.locator("nav[aria-label='Table of contents']");
    await expect(nav).toBeVisible();
    await expect(nav.locator(".toc-link").first()).toBeVisible();
  });

  test("page navigation works", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/page/3/");
    const nav = page.locator(".page-nav");
    await expect(nav).toBeVisible();
    await expect(nav.locator("a").first()).toBeVisible();
  });

  test("renders block content", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/page/5/");
    // Page 5 should have headings or paragraphs
    const blocks = page.locator(
      ".block-heading, .block-paragraph, .block-list, .block-figure"
    );
    await expect(blocks.first()).toBeVisible();
  });
});

test.describe("Multi-document", () => {
  test("second document landing page loads", async ({ page }) => {
    await page.goto("/docs/fixture-odyssey/");
    await expect(page.locator(".doc-landing h1")).toBeVisible();
  });

  test("second document reader page loads", async ({ page }) => {
    await page.goto("/docs/fixture-odyssey/page/1/");
    await expect(page.locator(".doc-content")).toBeVisible();
  });

  test("facsimile page shows placeholder", async ({ page }) => {
    await page.goto("/docs/fixture-odyssey/page/2/");
    await expect(page.locator(".page-view-facsimile")).toBeVisible();
    await expect(page.locator(".facsimile-placeholder")).toBeVisible();
  });
});

test.describe("App shell", () => {
  test("has header with site title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".app-header")).toBeVisible();
    await expect(page.locator(".app-title")).toContainText("Aeon Trespass");
  });

  test("has skip-to-content link", async ({ page }) => {
    await page.goto("/");
    const skipLink = page.locator(".skip-link");
    await expect(skipLink).toBeAttached();
  });

  test("has footer", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".app-footer")).toBeVisible();
  });
});
