import { test, expect } from "@playwright/test";

test.describe("Visual smoke tests", () => {
  test("catalog page renders correctly", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".catalog-page")).toBeVisible();
    await expect(page).toHaveScreenshot("catalog.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  test("reader page renders content", async ({ page }) => {
    await page.goto("/docs/aeon-trespass-core/page/3/");
    await expect(page.locator(".doc-content")).toBeVisible();
    await expect(page).toHaveScreenshot("reader-page.png", {
      maxDiffPixelRatio: 0.01,
    });
  });
});
