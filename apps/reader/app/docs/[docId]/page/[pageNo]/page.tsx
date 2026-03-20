/**
 * Reader page route — renders a single page from the bundle.
 */

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  docExists,
  listDocIds,
  loadBundleManifest,
  loadBundlePage,
  loadGlossary,
  loadNavigation,
  pageExists,
} from "@/lib/bundle";
import { pageRoute } from "@/lib/routes";
import { DocLayout } from "@/components/DocLayout";
import { PageView } from "@/components/PageView";
import { PageNav } from "@/components/PageNav";
import { SITE_URL } from "@/lib/seo";

export const dynamicParams = false;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ docId: string; pageNo: string }>;
}): Promise<Metadata> {
  const { docId, pageNo: pageNoStr } = await params;
  const pageNo = parseInt(pageNoStr, 10);
  if (!docExists(docId) || isNaN(pageNo) || !pageExists(docId, pageNo)) return {};
  const manifest = loadBundleManifest(docId);
  const title = `Page ${pageNo} — ${manifest.title_ru || manifest.title_en}`;
  const description = `Page ${pageNo} of ${manifest.page_count} — ${manifest.title_en}`;
  return {
    title,
    description,
    alternates: { canonical: `${SITE_URL}${pageRoute(docId, pageNo)}` },
    openGraph: { title, description, type: "article", locale: "ru_RU" },
    twitter: { card: "summary", title, description },
  };
}

export async function generateStaticParams() {
  const docIds = listDocIds();
  const params: { docId: string; pageNo: string }[] = [];
  for (const docId of docIds) {
    const manifest = loadBundleManifest(docId);
    for (let p = 1; p <= manifest.page_count; p++) {
      params.push({ docId, pageNo: String(p) });
    }
  }
  return params;
}

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ docId: string; pageNo: string }>;
}) {
  const { docId, pageNo: pageNoStr } = await params;
  const pageNo = parseInt(pageNoStr, 10);

  if (!docExists(docId) || isNaN(pageNo) || !pageExists(docId, pageNo)) {
    notFound();
  }

  const manifest = loadBundleManifest(docId);
  const navigation = loadNavigation(docId);
  const glossary = loadGlossary(docId);
  const page = loadBundlePage(docId, pageNo);

  return (
    <DocLayout
      manifest={manifest}
      navigation={navigation}
      glossaryEntries={glossary?.entries}
    >
      <PageView page={page} />
      <PageNav
        docId={docId}
        currentPage={pageNo}
        totalPages={manifest.page_count}
      />
    </DocLayout>
  );
}
