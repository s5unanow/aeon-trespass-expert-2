/**
 * Glossary page — lists all terms for the current document.
 */

import { notFound } from "next/navigation";
import {
  docExists,
  listDocIds,
  loadBundleManifest,
  loadGlossary,
  loadNavigation,
} from "@/lib/bundle";
import { DocLayout } from "@/components/DocLayout";
import { GlossaryTermList } from "@/components/GlossaryTermList";

export const dynamicParams = false;

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
