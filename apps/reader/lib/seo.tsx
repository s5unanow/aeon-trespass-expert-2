/**
 * SEO constants and helpers — shared metadata utilities.
 */

import type { Metadata } from "next";

/**
 * Base URL for the site. Used in OG tags, sitemap, and canonical URLs.
 * Override via NEXT_PUBLIC_SITE_URL environment variable.
 */
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://aeon-trespass-reader.pages.dev";

export const SITE_NAME = "Aeon Trespass Reader";
export const SITE_DESCRIPTION =
  "Translated rulebook reader for Aeon Trespass (EN\u2192RU)";

/** Shared OG / Twitter metadata defaults. */
export const sharedMetadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "ru_RU",
  },
  twitter: {
    card: "summary",
  },
  robots: {
    index: true,
    follow: true,
  },
};

/** Build a JSON-LD script element for structured data. */
export function jsonLd(data: Record<string, unknown>): React.ReactElement {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
