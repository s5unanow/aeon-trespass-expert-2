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
        {entries.length === 0 ? (
          <p className="glossary-empty">
            No glossary terms available for this document.
          </p>
        ) : (
          <dl className="glossary-term-list">
            {entries.map((entry) => (
              <div key={entry.term_id} className="glossary-term-item">
                <dt className="glossary-term-name">
                  {entry.ru_preferred}
                  <span className="glossary-term-en">{entry.en_canonical}</span>
                </dt>
                {entry.definition_ru && (
                  <dd className="glossary-term-def">{entry.definition_ru}</dd>
                )}
              </div>
            ))}
          </dl>
        )}
      </div>
    </DocLayout>
  );
}
