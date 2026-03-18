/**
 * DocLayout — document-level layout with sidebar and content area.
 */

import type {
  BundleGlossaryEntry,
  NavigationTree,
  SiteBundleManifest,
} from "@aeon-reader/contracts";
import { DocSidebar } from "./DocSidebar";
import { GlossaryDrawer } from "./GlossaryDrawer";

interface DocLayoutProps {
  manifest: SiteBundleManifest;
  navigation: NavigationTree | null;
  glossaryEntries?: BundleGlossaryEntry[];
  children: React.ReactNode;
}

export function DocLayout({
  manifest,
  navigation,
  glossaryEntries,
  children,
}: DocLayoutProps) {
  return (
    <div className="doc-layout">
      <DocSidebar manifest={manifest} navigation={navigation} />
      <article className="doc-content">{children}</article>
      {glossaryEntries && glossaryEntries.length > 0 && (
        <GlossaryDrawer entries={glossaryEntries} />
      )}
    </div>
  );
}
