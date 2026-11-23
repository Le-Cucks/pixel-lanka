# Pixel Lanka: run `make help` for the list of targets.
.DEFAULT_GOAL := help
WORKERS ?=
W := $(if $(WORKERS),--workers $(WORKERS),)

.PHONY: help setup data tiles island colombo landmarks dev build lint test typecheck check clean-out

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python (uv) and Node dependencies
	uv sync
	cd site && npm ci

data: ## Download Overture data for Sri Lanka and Colombo (~15 min, ~2.4 GB)
	uv run pipeline/fetch_overture.py sri-lanka
	uv run pipeline/fetch_overture.py colombo

tiles: island colombo landmarks ## Render every map and the landmark cards

island: ## Render the whole-island base map (~30 min)
	uv run pipeline/tiles.py island $(W)

colombo: ## Render the Colombo detail overlay (~1 min)
	uv run pipeline/tiles.py colombo $(W)

landmarks: ## Snap landmarks to the data and render their thumbnails
	uv run pipeline/landmarks.py

dev: ## Run the site at http://localhost:3000
	cd site && npm run dev

build: ## Production build of the site
	cd site && npm run build

lint: ## Lint Python (ruff) and TypeScript (eslint)
	uv run ruff check pipeline tests
	cd site && npm run lint

typecheck: ## Type-check the site
	cd site && npm run typecheck

test: ## Run the Python unit tests
	uv run pytest

check: lint typecheck test ## Everything CI runs, except the production build

clean-out: ## Delete single-image previews written by render.py
	rm -rf out
