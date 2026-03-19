/**
 * DocSidebar — sidebar navigation for a document.
 */

import Link from "next/link";
import type { NavigationTree, SiteBundleManifest } from "@aeon-reader/contracts";
import { docRoute } from "@/lib/routes";
import { DocTitle } from "./DocTitle";
import { TocTree } from "./TocTree";

interface DocSidebarProps {
  manifest: SiteBundleManifest;
  navigation: NavigationTree | null;
}

export function DocSidebar({ manifest, navigation }: DocSidebarProps) {
  return (
    <aside className="doc-sidebar">
      <div className="doc-sidebar-header">
        <Link href={docRoute(manifest.doc_id)} className="doc-sidebar-title">
          <DocTitle titleEn={manifest.title_en} titleRu={manifest.title_ru} />
        </Link>
      </div>
      {navigation && navigation.entries.length > 0 && (
        <nav className="doc-sidebar-nav" aria-label="Table of contents">
          <TocTree entries={navigation.entries} docId={manifest.doc_id} />
        </nav>
      )}
    </aside>
  );
}
