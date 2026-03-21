---
globs: apps/reader/**
---

# Reader conventions

- **Styling**: CSS Modules only — no inline styles, no global CSS outside `globals.css`
- **Static export**: The reader is a pure static site (`next export`). No server-side runtime.
- **Dev server port**: Use port 3002 (`pnpm dev -p 3002`)
- **Types**: All shared types come from `packages/contracts/`. Never write manual TS types for pipeline data.
- **Bundle sync**: The reader consumes pipeline output from `artifacts/`. Run the pipeline before verifying reader changes.
