---
globs: packages/pipeline/**/*.py,tests/**/*.py
---

# Pipeline conventions

- **JSON IO**: Always use `orjson` with atomic writes (write to temp file, then `os.rename`)
- **Config hashing**: Deterministic SHA-256 for cache keys and reproducibility
- **Contract direction**: Pydantic models are source of truth. Flow: Python Pydantic → JSON Schema → TypeScript. Never write manual TS types.
- **Stage implementations** go in `packages/pipeline/src/aeon_reader_pipeline/stages/`
- **Stage order**: See `docs/PIPELINE_STAGES.md` for the 16-stage canonical order. Registry: `stage_framework/registry.py`
- **Import boundaries**: Models must not import stages, LLM must not import stages. Verify with `uv run lint-imports`
- **Error handling**: No bare `except Exception` without structured logging via `structlog`
