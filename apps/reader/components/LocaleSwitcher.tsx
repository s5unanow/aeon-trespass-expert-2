"use client";

import { useLocale } from "@/lib/locale";

export function LocaleSwitcher() {
  const { locale, toggle } = useLocale();

  return (
    <button
      className="locale-switcher"
      onClick={toggle}
      type="button"
      aria-label={`Switch to ${locale === "ru" ? "English" : "Russian"}`}
      title={`Viewing: ${locale === "ru" ? "Russian" : "English"}`}
    >
      <span
        className={`locale-option ${locale === "en" ? "locale-option-active" : ""}`}
      >
        EN
      </span>
      <span className="locale-divider">/</span>
      <span
        className={`locale-option ${locale === "ru" ? "locale-option-active" : ""}`}
      >
        RU
      </span>
    </button>
  );
}
