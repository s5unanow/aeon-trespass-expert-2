/**
 * Glossary page — lists all terms for the current document.
 *
 * V1: placeholder. Full glossary rendering deferred to EP-010.
 */

import { notFound } from "next/navigation";
import { docExists, listDocIds, loadBundleManifest, loadNavigation } from "@/lib/bundle";
import { DocLayout } from "@/components/DocLayout";

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

  return (
    <DocLayout manifest={manifest} navigation={navigation}>
      <div className="glossary-page">
        <h1>Glossary</h1>
        <p>Glossary terms for {manifest.title_en}.</p>
        {!manifest.has_glossary && (
          <p className="glossary-empty">No glossary terms available for this document.</p>
        )}
      </div>
    </DocLayout>
  );
}
