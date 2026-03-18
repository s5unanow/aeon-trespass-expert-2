/**
 * SearchDialog — modal search dialog powered by Pagefind.
 *
 * Loads Pagefind lazily on first open. Results link to page routes.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { search, type PagefindResult } from "@/lib/pagefind";
import { trapFocus } from "@/lib/a11y";

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

export function SearchDialog({ open, onClose }: SearchDialogProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PagefindResult[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      const dialog = dialogRef.current;
      if (dialog) return trapFocus(dialog);
    } else {
      setQuery("");
      setResults([]);
    }
  }, [open]);

  const handleSearch = useCallback(async (q: string) => {
    setQuery(q);
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    const r = await search(q);
    setResults(r);
    setLoading(false);
  }, []);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && open) {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="search-overlay" onClick={onClose} role="presentation">
      <dialog
        ref={dialogRef}
        className="search-dialog"
        open
        onClick={(e) => e.stopPropagation()}
        aria-label="Search"
      >
        <div className="search-header">
          <input
            ref={inputRef}
            type="search"
            className="search-input"
            placeholder="Search..."
            value={query}
            onChange={(e) => handleSearch(e.target.value)}
            aria-label="Search query"
          />
          <button onClick={onClose} className="search-close" type="button" aria-label="Close search">
            &times;
          </button>
        </div>
        <div className="search-results" role="list" aria-label="Search results">
          {loading && <p className="search-loading">Searching...</p>}
          {!loading && query && results.length === 0 && (
            <p className="search-empty">No results found.</p>
          )}
          {results.map((result, i) => (
            <a
              key={i}
              href={result.url}
              className="search-result"
              role="listitem"
            >
              <span
                className="search-excerpt"
                dangerouslySetInnerHTML={{ __html: result.excerpt }}
              />
            </a>
          ))}
        </div>
      </dialog>
    </div>
  );
}
