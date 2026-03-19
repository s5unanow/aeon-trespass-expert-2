/**
 * AppShell — top-level layout shell with navigation chrome.
 */

import Link from "next/link";
import { catalogRoute } from "@/lib/routes";
import { LocaleSwitcher } from "./LocaleSwitcher";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <header className="app-header">
        <nav className="app-nav">
          <Link href={catalogRoute()} className="app-title">
            Aeon Trespass Reader
          </Link>
          <LocaleSwitcher />
        </nav>
      </header>
      <main id="main-content" className="app-main">{children}</main>
      <footer className="app-footer">
        <p>&copy; Aeon Trespass Reader</p>
      </footer>
    </div>
  );
}
