/**
 * Pagefind adapter — lazy-loaded search integration.
 *
 * Imports Pagefind only on first search open to avoid bloating
 * the initial page bundle.
 */

export interface PagefindResult {
  url: string;
  excerpt: string;
  meta?: Record<string, string>;
}

interface PagefindInstance {
  search: (query: string) => Promise<{ results: PagefindResultRaw[] }>;
  debouncedSearch: (query: string) => Promise<{ results: PagefindResultRaw[] } | null>;
}

interface PagefindResultRaw {
  data: () => Promise<PagefindResult>;
}

let pagefindInstance: PagefindInstance | null = null;

/**
 * Lazily load and initialize Pagefind.
 * Returns null if Pagefind is not available (e.g., no index built).
 */
export async function getPagefind(): Promise<PagefindInstance | null> {
  if (pagefindInstance) return pagefindInstance;

  try {
    // Pagefind places its JS at /pagefind/pagefind.js in the built site.
    // Dynamic import with string concatenation to avoid TS module resolution.
    const pagefindPath = "/pagefind/pagefind.js";
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const pf = await import(/* webpackIgnore: true */ /* @vite-ignore */ pagefindPath);
    pagefindInstance = pf as PagefindInstance;
    return pagefindInstance;
  } catch {
    console.warn("Pagefind not available — search index may not be built yet.");
    return null;
  }
}

/**
 * Search using Pagefind and return resolved results.
 */
export async function search(query: string, limit = 10): Promise<PagefindResult[]> {
  const pf = await getPagefind();
  if (!pf || !query.trim()) return [];

  const response = await pf.debouncedSearch(query);
  if (!response) return [];

  const results = await Promise.all(
    response.results.slice(0, limit).map((r) => r.data())
  );
  return results;
}
