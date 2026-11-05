.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck test check build

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:  ## create the venv and install the git hooks
	uv sync
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

lint:  ## ruff lint + format check and import layers, no changes
	uv run ruff check
	uv run ruff format --check
	uv run lint-imports

format:  ## ruff auto-fix + format
	uv run ruff check --fix
	uv run ruff format

typecheck:  ## pyright: strict on src/, standard on tests/
	uv run pyright

test:  ## unit tests
	uv run pytest

check: lint typecheck test  ## everything CI runs

build:  ## sdist and wheel into dist/
	uv build
