import type { MetadataRoute } from "next";
import { loadCatalog, loadBundleManifest } from "@/lib/bundle";
import { catalogRoute, docRoute, pageRoute, glossaryRoute } from "@/lib/routes";
import { SITE_URL } from "@/lib/seo";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const catalog = loadCatalog();
  const entries: MetadataRoute.Sitemap = [];

  // Catalog landing
  entries.push({
    url: `${SITE_URL}${catalogRoute()}`,
    changeFrequency: "weekly",
    priority: 1.0,
  });

  for (const doc of catalog.documents) {
    const manifest = loadBundleManifest(doc.doc_id);

    // Document landing
    entries.push({
      url: `${SITE_URL}${docRoute(doc.doc_id)}`,
      changeFrequency: "weekly",
      priority: 0.9,
    });

    // Individual pages
    for (let p = 1; p <= manifest.page_count; p++) {
      entries.push({
        url: `${SITE_URL}${pageRoute(doc.doc_id, p)}`,
        changeFrequency: "monthly",
        priority: 0.7,
      });
    }

    // Glossary
    entries.push({
      url: `${SITE_URL}${glossaryRoute(doc.doc_id)}`,
      changeFrequency: "monthly",
      priority: 0.5,
    });
  }

  return entries;
}
