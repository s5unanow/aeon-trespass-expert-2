#!/usr/bin/env node
/**
 * Programmatic assertions for the reader site.
 * Checks that key pages load, have content, and produce no JS errors.
 *
 * Requires: Playwright (pnpm exec playwright install chromium)
 * Usage: node .claude/skills/verify-reader/scripts/assert-pages.mjs
 */

const PORT = 3002;
const BASE_URL = `http://localhost:${PORT}`;
const DOC_SLUG = "aeon-trespass-core";

// Pages to check (page numbers)
const PAGES_TO_CHECK = [1, 3, 10, 35];

// URLs to check beyond page routes
const EXTRA_URLS = [
  "/",
  `/docs/${DOC_SLUG}`,
];

let exitCode = 0;

function pass(msg) {
  console.log(`  ✓ ${msg}`);
}

function fail(msg) {
  console.error(`  ✗ ${msg}`);
  exitCode = 1;
}

async function main() {
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    console.error("Playwright not installed. Run: pnpm exec playwright install chromium");
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  // Collect console errors per page
  const consoleErrors = [];

  try {
    // Check extra URLs (home, doc index)
    for (const path of EXTRA_URLS) {
      const url = `${BASE_URL}${path}`;
      console.log(`\nChecking ${url}`);

      const page = await context.newPage();
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push({ url, text: msg.text() });
      });

      const response = await page.goto(url, { waitUntil: "networkidle", timeout: 15000 }).catch(() => null);

      if (!response) {
        fail(`Failed to load ${url}`);
        await page.close();
        continue;
      }

      if (response.status() === 200) {
        pass(`HTTP 200`);
      } else {
        fail(`HTTP ${response.status()}`);
      }

      await page.close();
    }

    // Check document pages
    for (const pageNum of PAGES_TO_CHECK) {
      const url = `${BASE_URL}/docs/${DOC_SLUG}/page/${pageNum}`;
      console.log(`\nChecking page ${pageNum} (${url})`);

      const page = await context.newPage();
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push({ url, text: msg.text() });
      });

      const response = await page.goto(url, { waitUntil: "networkidle", timeout: 15000 }).catch(() => null);

      if (!response) {
        fail(`Failed to load page ${pageNum}`);
        await page.close();
        continue;
      }

      // HTTP status
      if (response.status() === 200) {
        pass("HTTP 200");
      } else {
        fail(`HTTP ${response.status()}`);
        await page.close();
        continue;
      }

      // Content present (body has meaningful text)
      const bodyText = await page.evaluate(() => document.body?.innerText?.trim() || "");
      if (bodyText.length > 50) {
        pass(`Content present (${bodyText.length} chars)`);
      } else {
        fail(`Insufficient content (${bodyText.length} chars — page may be blank)`);
      }

      // Sidebar/navigation exists
      const hasSidebar = await page.evaluate(() => {
        return !!(document.querySelector("nav") || document.querySelector("[class*='sidebar']") || document.querySelector("[class*='Sidebar']"));
      });
      if (hasSidebar) {
        pass("Sidebar/nav found");
      } else {
        fail("No sidebar/nav element found");
      }

      // Check for broken images
      const brokenImages = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll("img"));
        return imgs.filter((img) => !img.complete || img.naturalWidth === 0).map((img) => img.src);
      });
      if (brokenImages.length === 0) {
        pass("No broken images");
      } else {
        fail(`${brokenImages.length} broken image(s): ${brokenImages.slice(0, 3).join(", ")}`);
      }

      await page.close();
    }

    // Report console errors
    if (consoleErrors.length > 0) {
      console.log("\n--- Console Errors ---");
      for (const { url, text } of consoleErrors.slice(0, 10)) {
        fail(`Console error on ${url}: ${text.slice(0, 200)}`);
      }
    } else {
      console.log("\n--- Console Errors ---");
      pass("No console errors");
    }
  } finally {
    await browser.close();
  }

  console.log(`\n${exitCode === 0 ? "ALL CHECKS PASSED" : "SOME CHECKS FAILED"}`);
  process.exit(exitCode);
}

main().catch((err) => {
  console.error("Assertion script failed:", err.message);
  process.exit(1);
});
