/**
 * PageNav — previous/next page navigation controls.
 */

import Link from "next/link";
import { pageRoute } from "@/lib/routes";

interface PageNavProps {
  docId: string;
  currentPage: number;
  totalPages: number;
}

export function PageNav({ docId, currentPage, totalPages }: PageNavProps) {
  const hasPrev = currentPage > 1;
  const hasNext = currentPage < totalPages;

  return (
    <nav className="page-nav" aria-label="Page navigation">
      {hasPrev ? (
        <Link
          href={pageRoute(docId, currentPage - 1)}
          className="page-nav-link page-nav-prev"
        >
          &larr; Page {currentPage - 1}
        </Link>
      ) : (
        <span className="page-nav-placeholder" />
      )}
      <span className="page-nav-current">
        Page {currentPage} of {totalPages}
      </span>
      {hasNext ? (
        <Link
          href={pageRoute(docId, currentPage + 1)}
          className="page-nav-link page-nav-next"
        >
          Page {currentPage + 1} &rarr;
        </Link>
      ) : (
        <span className="page-nav-placeholder" />
      )}
    </nav>
  );
}
