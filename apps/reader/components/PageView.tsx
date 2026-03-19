/**
 * PageView — renders a full BundlePage as a sequence of blocks.
 *
 * Supports three render modes:
 * - semantic: Full block rendering (headings, paragraphs, lists, etc.)
 * - hybrid: Block rendering with fallback image available
 * - facsimile: Full-page fallback image, no semantic blocks
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
      {page.render_mode === "facsimile" ? (
        <FacsimileView page={page} />
      ) : (
        <>
          {page.blocks.map((block) => (
            <BlockRenderer key={block.block_id} block={block} />
          ))}
          {page.render_mode === "hybrid" && page.fallback_image_ref && (
            <details className="hybrid-fallback">
              <summary>View original page</summary>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={page.fallback_image_ref}
                alt={`Original page ${page.page_number}`}
                className="fallback-image"
                loading="lazy"
              />
            </details>
          )}
        </>
      )}
    </section>
  );
}

function FacsimileView({ page }: PageViewProps) {
  if (page.fallback_image_ref) {
    return (
      <div className="facsimile-page">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={page.fallback_image_ref}
          alt={`Page ${page.page_number} (original scan)`}
          className="fallback-image"
          loading="lazy"
        />
      </div>
    );
  }
  return (
    <div className="facsimile-page facsimile-placeholder">
      <p>
        This page is available in its original layout only. Semantic content is
        not available for this page.
      </p>
    </div>
  );
}
