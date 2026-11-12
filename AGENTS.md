# AGENTS.md

nuikit is a library: config schemas validated from Hydra, YAML mirrors, families chosen by `kind`, user errors with
exit codes, logging, run directories and seeding. Projects from nuinashco/rnd-template depend on it, and `plugin/` is
the Claude Code plugin that teaches them its patterns. How it is built: [CONTRIBUTING.md](CONTRIBUTING.md).

## Rules

- This repo follows [nuinashco/conventions](https://github.com/nuinashco/conventions) (the `conventions` plugin
  brings its rules and hooks) and [docs/guide.md](docs/guide.md), which holds the rules that name nuikit's API (FAM,
  CFG, ERR-1, ERR-2, LOG-1, LOG-3, RUN-1, RUN-2). Code here is held to them like any project's.
- Keep the public API stable: every module-level name without a leading underscore in the seven modules, all listed
  in [docs/api.md](docs/api.md). A rename or changed signature is a breaking change; versions follow semver, and
  until 1.0 a breaking change bumps the minor version. A new public name gets a row there, which a test checks.
- A rule change edits `docs/guide.md`, the code and tests its *Check* names, and the skills that show the pattern, in
  one commit. Rule IDs are never renamed or reused.
- Skills in `plugin/skills/` show code exactly as the guide asks; `make test` renders their family templates and runs
  them, so keep the `<placeholders>` and `tests/test_plugin.py` in step.
- Python floor 3.12: every module starts with `from __future__ import annotations`; ASCII in `.py` files.
- Commits: one line, Conventional Commits, lowercase imperative subject, no articles, no body or trailers.

## Commands

```bash
make setup        # uv sync + git hooks (pre-commit, commit-msg)
make check        # ruff, the conventions checks, import layers, pyright (strict on src/), pytest: before every commit
make format       # ruff fixes + format
```

## Layout

- `src/nuikit/`: `config`, `configgen`, `registry`, `errors`, `logging`, `runs`, `seeding`; the layers contract in
  `pyproject.toml` fixes which may import which.
- `tests/`: one module per library module, plus `test_plugin.py` (skills), `test_docs.py` and `test_imports.py`;
  fakes live in `conftest.py`.
- `docs/guide.md`: the nuikit rules; `docs/api.md`: every public name. `plugin/`: `.claude-plugin/plugin.json` and
  `skills/<name>/SKILL.md`.
- Releases are tags `vX.Y.Z` on `main` matching `version` in `pyproject.toml`; projects install nuikit from the tag.
