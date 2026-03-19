"use client";

import type { BundleGlossaryEntry } from "@aeon-reader/contracts";
import { useLocale } from "@/lib/locale";

interface GlossaryTermListProps {
  entries: BundleGlossaryEntry[];
}

export function GlossaryTermList({ entries }: GlossaryTermListProps) {
  const { locale } = useLocale();

  if (entries.length === 0) {
    return (
      <p className="glossary-empty">
        No glossary terms available for this document.
      </p>
    );
  }

  return (
    <dl className="glossary-term-list">
      {entries.map((entry) => {
        const primary =
          locale === "ru" ? entry.ru_preferred : entry.en_canonical;
        const secondary =
          locale === "ru" ? entry.en_canonical : entry.ru_preferred;
        const definition =
          locale === "ru" ? entry.definition_ru : entry.definition_en;

        return (
          <div key={entry.term_id} className="glossary-term-item">
            <dt className="glossary-term-name">
              {primary}
              <span className="glossary-term-en">{secondary}</span>
            </dt>
            {definition && (
              <dd className="glossary-term-def">{definition}</dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}
