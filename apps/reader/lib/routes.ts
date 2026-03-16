/**
 * Route helpers — URL generation and param validation.
 */

/** Route to the catalog landing page. */
export function catalogRoute(): string {
  return "/";
}

/** Route to a document landing page. */
export function docRoute(docId: string): string {
  return `/docs/${docId}/`;
}

/** Route to a specific page within a document. */
export function pageRoute(docId: string, pageNo: number): string {
  return `/docs/${docId}/page/${pageNo}/`;
}

/** Route to the glossary page for a document. */
export function glossaryRoute(docId: string): string {
  return `/docs/${docId}/glossary/`;
}

/** Parse document route params. */
export function parseDocParams(params: { docId: string }): {
  docId: string;
} {
  return { docId: params.docId };
}

/** Parse page route params. */
export function parsePageParams(params: { docId: string; pageNo: string }): {
  docId: string;
  pageNo: number;
} {
  return {
    docId: params.docId,
    pageNo: parseInt(params.pageNo, 10),
  };
}
