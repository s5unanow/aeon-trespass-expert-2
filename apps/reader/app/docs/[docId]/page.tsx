/**
 * Document landing page — shows document info and entry point.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { docExists, listDocIds, loadBundleManifest, loadNavigation } from "@/lib/bundle";
import { pageRoute, glossaryRoute } from "@/lib/routes";
import { DocLayout } from "@/components/DocLayout";

export const dynamicParams = false;

export async function generateStaticParams() {
  return listDocIds().map((docId) => ({ docId }));
}

export default async function DocLandingPage({
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
      <div className="doc-landing">
        <h1>{manifest.title_en}</h1>
        {manifest.title_ru && <p className="doc-subtitle">{manifest.title_ru}</p>}
        <dl className="doc-meta">
          <dt>Pages</dt>
          <dd>{manifest.page_count}</dd>
          <dt>Translation</dt>
          <dd>{Math.round(manifest.translation_coverage * 100)}%</dd>
          <dt>Languages</dt>
          <dd>
            {manifest.source_locale} &rarr; {manifest.target_locale}
          </dd>
        </dl>
        <nav className="doc-entry-links">
          <Link href={pageRoute(docId, 1)} className="doc-start-link">
            Start reading &rarr;
          </Link>
          <Link href={glossaryRoute(docId)} className="doc-glossary-link">
            Glossary
          </Link>
        </nav>
      </div>
    </DocLayout>
  );
}
