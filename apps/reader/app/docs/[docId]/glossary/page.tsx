/**
 * Glossary page — lists all terms for the current document.
 */

import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  docExists,
  listDocIds,
  loadBundleManifest,
  loadGlossary,
  loadNavigation,
} from "@/lib/bundle";
import { glossaryRoute } from "@/lib/routes";
import { DocLayout } from "@/components/DocLayout";
import { GlossaryTermList } from "@/components/GlossaryTermList";
import { SITE_URL } from "@/lib/seo";

export const dynamicParams = false;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ docId: string }>;
}): Promise<Metadata> {
  const { docId } = await params;
  if (!docExists(docId)) return {};
  const manifest = loadBundleManifest(docId);
  const title = `Glossary — ${manifest.title_ru || manifest.title_en}`;
  const description = `Translation glossary for ${manifest.title_en}`;
  return {
    title,
    description,
    alternates: { canonical: `${SITE_URL}${glossaryRoute(docId)}` },
    openGraph: { title, description, locale: "ru_RU" },
    twitter: { card: "summary", title, description },
  };
}

export async function generateStaticParams() {
  return listDocIds().map((docId) => ({ docId }));
}

export default async function GlossaryPage({
  params,
}: {
  params: Promise<{ docId: string }>;
}) {
  const { docId } = await params;

  if (!docExists(docId)) {
    notFound();
  }

  const manifest = loadBundleManifest(docId);
  const navigation = loadNavigation(docId);
  const glossary = loadGlossary(docId);
  const entries = glossary?.entries ?? [];

  return (
    <DocLayout
      manifest={manifest}
      navigation={navigation}
      glossaryEntries={entries}
    >
      <div className="glossary-page">
        <h1>Glossary</h1>
        <GlossaryTermList entries={entries} />
      </div>
    </DocLayout>
  );
}
