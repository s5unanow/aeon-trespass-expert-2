.PHONY: help bootstrap lint typecheck test test-backend test-frontend schemas \
        site-dev site-build build-search site-release e2e clean security-lint deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install all dependencies
	uv sync
	pnpm install

lint: ## Run all linters
	uv run ruff check packages/pipeline/src tests/backend
	uv run ruff format --check packages/pipeline/src tests/backend
	pnpm -r run lint

security-lint: ## Run security linter (bandit)
	uv run bandit -c pyproject.toml -r packages/pipeline/src

typecheck: ## Run all type checkers
	uv run mypy packages/pipeline/src
	pnpm -r run typecheck

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend tests
	uv run pytest tests/backend

test-frontend: ## Run frontend tests
	pnpm --filter reader test

schemas: ## Regenerate contracts from Pydantic models
	uv run python scripts/gen_contracts.py
	@echo "Contracts regenerated."

check-generated: schemas ## Verify generated files are up to date
	@git diff --exit-code packages/contracts/ || \
		(echo "ERROR: Generated contracts are out of date. Run 'make schemas'." && exit 1)
	@test -z "$$(git ls-files --others --exclude-standard packages/contracts/)" || \
		(echo "ERROR: Untracked contract files found. Commit them or run 'make schemas'." && exit 1)

site-dev: ## Start reader dev server
	pnpm --filter reader dev

site-build: ## Build static reader site
	pnpm --filter reader build

build-search: ## Build Pagefind search index (run after site-build)
	pnpm --filter reader run build:search

site-release: site-build build-search ## Full operator path: build site + search index
	@test -d apps/reader/out/pagefind || (echo "ERROR: Pagefind index not found at apps/reader/out/pagefind/" && exit 1)
	@echo "Site built with search index at apps/reader/out/"

e2e: ## Run end-to-end tests
	pnpm --filter reader test:e2e

deploy: site-build ## Full deploy: build static site (run pipeline first)
	@echo "Static site built at apps/reader/out/"
	@echo "Deploy by uploading apps/reader/out/ to your hosting provider."

clean: ## Remove build artifacts and caches
	rm -rf .mypy_cache .ruff_cache .pytest_cache
	rm -rf apps/reader/.next apps/reader/out
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
