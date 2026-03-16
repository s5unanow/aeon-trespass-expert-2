import type { Metadata } from "next";
import "@/styles/globals.css";
import "@/styles/theme.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Aeon Trespass Reader",
  description: "Translated rulebook reader for Aeon Trespass",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
