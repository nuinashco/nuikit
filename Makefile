.DEFAULT_GOAL := help
.PHONY: help setup github lint format typecheck test check
# Every Python file git does not ignore, NUL-separated so that a name with a space or a
# letter outside ASCII reaches the checks whole.
PYTHON_FILES = git ls-files -z -co --exclude-standard '*.py'

help:  ## show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:  ## create the venv and install the git hooks
	uv sync
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

github:  ## once per GitHub repo: squash-merge only, PR title as the commit, merged branches deleted
	gh api -X PATCH "repos/{owner}/{repo}" --silent \
		-F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
		-f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=BLANK \
		-F delete_branch_on_merge=true

lint:  ## ruff, the conventions checks on every Python file and import layers, no changes
	uv run ruff check
	uv run ruff format --check
	$(PYTHON_FILES) | xargs -0 uv run check-comments
	$(PYTHON_FILES) | xargs -0 uv run check-conventions
	uv run lint-imports

format:  ## ruff auto-fix + format
	uv run ruff check --fix
	uv run ruff format

typecheck:  ## pyright: strict on src/, standard on tests/
	uv run pyright

test:  ## unit tests
	uv run pytest

check: lint typecheck test  ## everything CI runs
