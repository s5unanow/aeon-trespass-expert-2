/**
 * GlossaryDrawer — slide-out drawer for glossary term lookup.
 *
 * Listens for clicks on `.inline-glossary-ref` elements via event delegation.
 * Shows term details (EN canonical, RU preferred, definitions) in a drawer.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { BundleGlossaryEntry } from "@aeon-reader/contracts";
import { trapFocus } from "@/lib/a11y";

interface GlossaryDrawerProps {
  entries: BundleGlossaryEntry[];
}

export function GlossaryDrawer({ entries }: GlossaryDrawerProps) {
  const [activeTerm, setActiveTerm] = useState<BundleGlossaryEntry | null>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const termMap = useRef<Map<string, BundleGlossaryEntry>>(new Map());

  // Build lookup map once
  useEffect(() => {
    const map = new Map<string, BundleGlossaryEntry>();
    for (const entry of entries) {
      map.set(entry.term_id, entry);
    }
    termMap.current = map;
  }, [entries]);

  const close = useCallback(() => setActiveTerm(null), []);

  // Event delegation: listen for clicks on glossary refs
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      const target = (e.target as HTMLElement).closest<HTMLElement>(".inline-glossary-ref");
      if (!target) return;
      const termId = target.dataset.termId;
      if (!termId) return;
      const entry = termMap.current.get(termId);
      if (entry) {
        e.preventDefault();
        setActiveTerm(entry);
      }
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  // Keyboard: Escape closes
  useEffect(() => {
    if (!activeTerm) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setActiveTerm(null);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [activeTerm]);

  // Focus trap, auto-focus close button, and body scroll lock
  useEffect(() => {
    if (!activeTerm) return;
    closeRef.current?.focus();
    document.body.style.overflow = "hidden";
    const drawer = drawerRef.current;
    const cleanupTrap = drawer ? trapFocus(drawer) : undefined;
    return () => {
      document.body.style.overflow = "";
      cleanupTrap?.();
    };
  }, [activeTerm]);

  if (!activeTerm) return null;

  return (
    <div className="glossary-backdrop" onClick={close} role="presentation">
      <aside
        ref={drawerRef}
        className="glossary-drawer"
        role="dialog"
        aria-label="Glossary term"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glossary-drawer-header">
          <h3 className="glossary-drawer-title">{activeTerm.ru_preferred}</h3>
          <button
            ref={closeRef}
            className="glossary-drawer-close"
            onClick={close}
            type="button"
            aria-label="Close glossary"
          >
            &times;
          </button>
        </div>
        <div className="glossary-drawer-body">
          <dl className="glossary-drawer-fields">
            <dt>English</dt>
            <dd>{activeTerm.en_canonical}</dd>
            <dt>Russian</dt>
            <dd>{activeTerm.ru_preferred}</dd>
          </dl>
          {activeTerm.definition_ru && (
            <div className="glossary-drawer-definition">
              <h4>Definition</h4>
              <p>{activeTerm.definition_ru}</p>
            </div>
          )}
          {activeTerm.definition_en && (
            <div className="glossary-drawer-definition">
              <h4>Definition (EN)</h4>
              <p>{activeTerm.definition_en}</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
