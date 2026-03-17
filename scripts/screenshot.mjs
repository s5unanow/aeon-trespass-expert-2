#!/usr/bin/env node
/**
 * Capture screenshots of reader pages for visual inspection.
 * Usage: node scripts/screenshot.mjs [page numbers...]
 * Default: captures pages 1, 3, 10, 35, 50, 70
 */
import { chromium } from "playwright";
import { mkdirSync } from "fs";

const BASE = "http://localhost:3000/docs/aeon-trespass-core/page";
const OUT_DIR = "artifacts/screenshots";
const DEFAULT_PAGES = [1, 3, 10, 35, 50, 70];

const pages = process.argv.slice(2).map(Number).filter(Boolean);
const pageNos = pages.length ? pages : DEFAULT_PAGES;

mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });

for (const p of pageNos) {
  const page = await ctx.newPage();
  await page.goto(`${BASE}/${p}`, { waitUntil: "networkidle" });
  const path = `${OUT_DIR}/page-${String(p).padStart(2, "0")}.png`;
  await page.screenshot({ path, fullPage: false });
  console.log(`Captured page ${p} -> ${path}`);
  await page.close();
}

await browser.close();
console.log("Done.");
