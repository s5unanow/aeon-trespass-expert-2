---
globs: packages/contracts/**
---

# Contract conventions

- **Source of truth**: Pydantic models in `packages/pipeline/` define all data shapes
- **Generation flow**: Python Pydantic → JSON Schema → TypeScript. Run `make schemas` to regenerate.
- **Never edit generated files directly** — changes will be overwritten on next `make schemas`
- **When to regenerate**: Any time a Pydantic model in the pipeline changes, run `make schemas` and commit the updated contracts
