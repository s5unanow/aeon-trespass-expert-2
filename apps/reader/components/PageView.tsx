/**
 * PageView — renders a full BundlePage as a sequence of blocks.
 */

import type { BundlePage } from "@aeon-reader/contracts";
import { BlockRenderer } from "./BlockRenderer";

interface PageViewProps {
  page: BundlePage;
}

export function PageView({ page }: PageViewProps) {
  return (
    <section
      className={`page-view page-view-${page.render_mode}`}
      data-page-number={page.page_number}
      aria-label={`Page ${page.page_number}`}
    >
      {page.blocks.map((block) => (
        <BlockRenderer key={block.block_id} block={block} />
      ))}
    </section>
  );
}
