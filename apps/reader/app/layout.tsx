import type { Metadata } from "next";
import "@/styles/globals.css";
import "@/styles/theme.css";
import { AppShell } from "@/components/AppShell";
import { LocaleProvider } from "@/lib/locale";
import { sharedMetadata } from "@/lib/seo";

export const metadata: Metadata = {
  ...sharedMetadata,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body>
        <LocaleProvider>
          <AppShell>{children}</AppShell>
        </LocaleProvider>
      </body>
    </html>
  );
}
