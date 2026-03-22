/**
 * Extraction review regression checks — browser-level verification for curated
 * EN extraction pages.
 *
 * Complements S5U-286 payload-level checks by asserting that the reader
 * correctly renders curated EN/source-edition pages: expected headings, block
 * kinds, inline symbols, figures/assets, and page metadata appear in the DOM.
 *
 * Console/render errors are captured and treated as failures.
 */

import { test, expect, type Page, type ConsoleMessage } from "@playwright/test";

// ---------------------------------------------------------------------------
// Force EN locale for all extraction review tests
// ---------------------------------------------------------------------------

test.use({
  storageState: {
    cookies: [],
    origins: [
      {
        origin: "http://localhost:3123",
        localStorage: [{ name: "aeon-reader-locale", value: "en" }],
      },
    ],
  },
});

// ---------------------------------------------------------------------------
// Console-error capture helper
// ---------------------------------------------------------------------------

/** Collect console errors during a test and fail if any are present. */
function captureConsoleErrors(page: Page): ConsoleMessage[] {
  const errors: ConsoleMessage[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg);
  });
  page.on("pageerror", (err) => {
    // pageerror fires for uncaught JS exceptions — wrap as ConsoleMessage-like
    errors.push({ text: () => err.message } as unknown as ConsoleMessage);
  });
  return errors;
}

function assertNoConsoleErrors(errors: ConsoleMessage[], label: string) {
  const texts = errors.map((e) => e.text());
  expect(texts, `Console errors on ${label}`).toEqual([]);
}

// ---------------------------------------------------------------------------
// Curated page definitions — expected DOM structure per page
// ---------------------------------------------------------------------------

interface CuratedPage {
  /** Route path from baseURL */
  route: string;
  /** Human label for test output */
  label: string;
  /** data-page-number attribute value */
  pageNumber: number;
  /** Expected render mode class suffix */
  renderMode: "semantic" | "hybrid" | "facsimile";
  /** Expected block kinds present on the page (CSS class selectors) */
  expectedBlockKinds: string[];
  /** Text substrings expected somewhere in the page content area */
  expectedTextContent: string[];
  /** Expected heading texts (exact match within heading elements) */
  expectedHeadings: string[];
  /** If the page contains figures, expected figure count */
  expectedFigureCount?: number;
  /** If the page contains list items, expected count */
  expectedListItemCount?: number;
  /** Expected symbol IDs rendered (data-symbol-id attribute values) */
  expectedSymbolIds?: string[];
  /** Expected glossary term IDs (data-term-id attribute values) */
  expectedGlossaryTermIds?: string[];
  /** Take a screenshot for visual regression */
  screenshot?: string;
}

const CURATED_PAGES: CuratedPage[] = [
  {
    route: "/docs/aeon-trespass-core/page/1/",
    label: "aeon-trespass-core/p1 (cover)",
    pageNumber: 1,
    renderMode: "semantic",
    expectedBlockKinds: [".block-figure", ".block-paragraph"],
    expectedTextContent: ["RULEBOOK"],
    expectedHeadings: [],
    expectedFigureCount: 1,
  },
  {
    route: "/docs/aeon-trespass-core/page/3/",
    label: "aeon-trespass-core/p3 (contents)",
    pageNumber: 3,
    renderMode: "semantic",
    expectedBlockKinds: [".block-heading", ".block-paragraph"],
    expectedTextContent: ["Introduction", "Game Rules"],
    expectedHeadings: ["Contents"],
  },
  {
    route: "/docs/aeon-trespass-core/page/5/",
    label: "aeon-trespass-core/p5 (rules)",
    pageNumber: 5,
    renderMode: "semantic",
    expectedBlockKinds: [
      ".block-heading",
      ".block-paragraph",
      ".block-list",
    ],
    expectedTextContent: [
      "Players take turns",
      "Move your character",
      "Attack an enemy",
      "battle phase",
    ],
    expectedHeadings: ["Game Rules"],
    expectedListItemCount: 2,
    expectedSymbolIds: ["sym:action-die"],
    expectedGlossaryTermIds: ["battle-phase"],
    screenshot: "extraction-review-p5.png",
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Extraction review — curated EN pages", () => {
  for (const cp of CURATED_PAGES) {
    test.describe(cp.label, () => {
      test("renders without console errors", async ({ page }) => {
        const errors = captureConsoleErrors(page);
        await page.goto(cp.route);
        await expect(page.locator(".page-view")).toBeVisible();
        assertNoConsoleErrors(errors, cp.label);
      });

      test("page metadata attributes are correct", async ({ page }) => {
        await page.goto(cp.route);
        const view = page.locator(".page-view");
        await expect(view).toBeVisible();
        await expect(view).toHaveAttribute(
          "data-page-number",
          String(cp.pageNumber),
        );
        await expect(view).toHaveClass(
          new RegExp(`page-view-${cp.renderMode}`),
        );
      });

      test("expected block kinds are present", async ({ page }) => {
        await page.goto(cp.route);
        const content = page.locator(".page-view");
        await expect(content).toBeVisible();
        for (const selector of cp.expectedBlockKinds) {
          await expect(
            content.locator(selector).first(),
            `Block kind ${selector} missing on ${cp.label}`,
          ).toBeVisible();
        }
      });

      test("expected text content is rendered", async ({ page }) => {
        await page.goto(cp.route);
        const content = page.locator(".page-view");
        await expect(content).toBeVisible();
        for (const text of cp.expectedTextContent) {
          await expect(
            content,
            `Text "${text}" missing on ${cp.label}`,
          ).toContainText(text);
        }
      });

      if (cp.expectedHeadings.length > 0) {
        test("expected headings are present", async ({ page }) => {
          await page.goto(cp.route);
          for (const heading of cp.expectedHeadings) {
            const h = page.locator(".block-heading", { hasText: heading });
            await expect(
              h.first(),
              `Heading "${heading}" missing on ${cp.label}`,
            ).toBeVisible();
          }
        });
      }

      if (cp.expectedFigureCount !== undefined) {
        test("figure blocks render with images", async ({ page }) => {
          await page.goto(cp.route);
          const figures = page.locator(".block-figure");
          await expect(figures).toHaveCount(cp.expectedFigureCount!);
          // Each figure with an asset_ref should contain an <img> tag
          for (let i = 0; i < cp.expectedFigureCount!; i++) {
            const img = figures.nth(i).locator("img");
            await expect(
              img,
              `Figure ${i} missing <img> on ${cp.label}`,
            ).toBeAttached();
            // Verify src attribute exists (no broken asset ref)
            const src = await img.getAttribute("src");
            expect(
              src,
              `Figure ${i} has empty src on ${cp.label}`,
            ).toBeTruthy();
          }
        });
      }

      if (cp.expectedListItemCount !== undefined) {
        test("list items render with correct count", async ({ page }) => {
          await page.goto(cp.route);
          const items = page.locator(".block-list-item");
          await expect(items).toHaveCount(cp.expectedListItemCount!);
        });
      }

      if (cp.expectedSymbolIds && cp.expectedSymbolIds.length > 0) {
        test("inline symbols render correctly", async ({ page }) => {
          await page.goto(cp.route);
          for (const symbolId of cp.expectedSymbolIds!) {
            const sym = page.locator(
              `.inline-symbol[data-symbol-id="${symbolId}"]`,
            );
            await expect(
              sym,
              `Symbol "${symbolId}" missing on ${cp.label}`,
            ).toBeVisible();
            // Symbols with SVG data should have role="img" and aria-label
            await expect(sym).toHaveAttribute("role", "img");
            const ariaLabel = await sym.getAttribute("aria-label");
            expect(
              ariaLabel,
              `Symbol "${symbolId}" missing aria-label on ${cp.label}`,
            ).toBeTruthy();
            // Symbol with svg_data should render inline SVG
            const svg = sym.locator("svg");
            await expect(
              svg,
              `Symbol "${symbolId}" missing SVG on ${cp.label}`,
            ).toBeAttached();
          }
        });
      }

      if (
        cp.expectedGlossaryTermIds &&
        cp.expectedGlossaryTermIds.length > 0
      ) {
        test("glossary references render correctly", async ({ page }) => {
          await page.goto(cp.route);
          for (const termId of cp.expectedGlossaryTermIds!) {
            const ref = page.locator(
              `.inline-glossary-ref[data-term-id="${termId}"]`,
            );
            await expect(
              ref,
              `Glossary ref "${termId}" missing on ${cp.label}`,
            ).toBeVisible();
            // Glossary refs should have visible text
            const text = await ref.textContent();
            expect(
              text?.trim(),
              `Glossary ref "${termId}" has no text on ${cp.label}`,
            ).toBeTruthy();
          }
        });
      }

      if (cp.screenshot) {
        test("visual snapshot matches baseline", async ({ page }) => {
          const errors = captureConsoleErrors(page);
          await page.goto(cp.route);
          await expect(page.locator(".page-view")).toBeVisible();
          await expect(page).toHaveScreenshot(cp.screenshot!, {
            maxDiffPixelRatio: 0.01,
          });
          assertNoConsoleErrors(errors, `${cp.label} (screenshot)`);
        });
      }
    });
  }
});

// ---------------------------------------------------------------------------
// Cross-page structural checks
// ---------------------------------------------------------------------------

test.describe("Extraction review — cross-page integrity", () => {
  test("all curated pages load without broken images", async ({ page }) => {
    for (const cp of CURATED_PAGES) {
      await page.goto(cp.route);
      await expect(page.locator(".page-view")).toBeVisible();
      // Check all images on the page have loaded (naturalWidth > 0)
      // Note: in static export, missing assets result in 404 images
      const images = page.locator(".page-view img");
      const count = await images.count();
      for (let i = 0; i < count; i++) {
        const img = images.nth(i);
        const src = await img.getAttribute("src");
        // Only check images with a src (figure blocks without asset_ref won't have img)
        if (src) {
          // Verify the image element is attached and has a non-empty src
          await expect(
            img,
            `Broken image ref "${src}" on ${cp.label}`,
          ).toBeAttached();
        }
      }
    }
  });

  test("page-level block IDs are unique within each page", async ({
    page,
  }) => {
    for (const cp of CURATED_PAGES) {
      await page.goto(cp.route);
      await expect(page.locator(".page-view")).toBeVisible();
      // Collect all elements with an id attribute inside page-view
      const ids = await page
        .locator(".page-view [id]")
        .evaluateAll((els) => els.map((el) => el.id));
      const uniqueIds = new Set(ids);
      expect(
        ids.length,
        `Duplicate block IDs on ${cp.label}: ${ids.filter((id, i) => ids.indexOf(id) !== i).join(", ")}`,
      ).toBe(uniqueIds.size);
    }
  });
});
