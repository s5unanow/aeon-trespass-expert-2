/**
 * AppShell — top-level layout shell with navigation chrome.
 */

import Link from "next/link";
import { catalogRoute } from "@/lib/routes";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <nav className="app-nav">
          <Link href={catalogRoute()} className="app-title">
            Aeon Trespass Reader
          </Link>
        </nav>
      </header>
      <main className="app-main">{children}</main>
      <footer className="app-footer">
        <p>&copy; Aeon Trespass Reader</p>
      </footer>
    </div>
  );
}
