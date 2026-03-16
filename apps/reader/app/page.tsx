/**
 * Catalog landing page — lists available documents.
 */

import Link from "next/link";
import { loadCatalog } from "@/lib/bundle";
import { docRoute } from "@/lib/routes";

export default function CatalogPage() {
  const catalog = loadCatalog();

  return (
    <div className="catalog-page">
      <h1>Aeon Trespass Reader</h1>
      {catalog.total_documents === 0 ? (
        <p>No documents available. Run the pipeline to generate content.</p>
      ) : (
        <ul className="catalog-list">
          {catalog.documents.map((doc) => (
            <li key={doc.doc_id} className="catalog-item">
              <Link href={docRoute(doc.doc_id)} className="catalog-link">
                <h2>{doc.title_en}</h2>
                {doc.title_ru && <p className="catalog-subtitle">{doc.title_ru}</p>}
                <p className="catalog-meta">
                  {doc.page_count} pages &middot;{" "}
                  {Math.round(doc.translation_coverage * 100)}% translated
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
