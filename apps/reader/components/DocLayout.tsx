/**
 * DocLayout — document-level layout with sidebar and content area.
 */

import type { NavigationTree, SiteBundleManifest } from "@aeon-reader/contracts";
import { DocSidebar } from "./DocSidebar";

interface DocLayoutProps {
  manifest: SiteBundleManifest;
  navigation: NavigationTree | null;
  children: React.ReactNode;
}

export function DocLayout({ manifest, navigation, children }: DocLayoutProps) {
  return (
    <div className="doc-layout">
      <DocSidebar manifest={manifest} navigation={navigation} />
      <article className="doc-content">{children}</article>
    </div>
  );
}
