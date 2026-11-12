# Contributing

How nuikit is built and how to change it. Using it: [README.md](README.md). It follows the general rules of
[nuinashco/conventions](https://github.com/nuinashco/conventions), and [docs/guide.md](docs/guide.md) holds the rules
that name its API.

## Architecture

```mermaid
flowchart TD
    registry["registry<br/>families, discovery by import, generated config files"]:::side
    configgen["configgen<br/>render schemas to YAML, rewrite stale files"]:::side
    runs["runs<br/>run directories, W&B mirror"]:::side
    config["config<br/>Schema, from_hydra"]:::pure
    errors["errors<br/>UserError family, cli_boundary"]:::side
    logging["logging<br/>configure_logging"]:::side
    seeding["seeding<br/>seed_everything"]:::side
    registry --> configgen & config & errors
    configgen --> config & errors
    runs --> config & errors
    config --> errors
    pure["teal: decides, same input same output"]:::pure
    side["rust: acts on files, processes, global state"]:::side
    classDef pure fill:#d9f2ec,stroke:#1b7f6b,color:#0b3d33
    classDef side fill:#f8e3d8,stroke:#b4532a,color:#4a1f0c
```

Dependencies point down. The import-linter layers contract in `pyproject.toml` enforces it and is exhaustive, so a
new module fails `make check` until it is placed: `registry`, then `configgen | runs`, then `config`, then
`errors | logging | seeding`. Modules in one layer never import each other. Heavy optional modules (`wandb`,
`torch`) are imported inside the function that needs them, so `import nuikit` stays cheap and the extras stay
optional.

## Repository layout

```text
src/nuikit/           the library, one module per concern; py.typed ships its types
tests/                one test module per library module; test_plugin.py renders the skill templates;
                      conftest.py holds the fakes
docs/guide.md         FAM, CFG, ERR-1, ERR-2, LOG-1, LOG-3, RUN-1, RUN-2: the rules for code that uses nuikit
docs/api.md           every public name, a row each
plugin/               the Claude Code plugin `nuikit`
  .claude-plugin/     plugin.json, without a version, so installs follow commits
  skills/<name>/      SKILL.md, plus templates/*.tmpl with <placeholders> to fill
.github/workflows/    ci.yml: `make check` on Python 3.12 and 3.14
.claude/settings.json the conventions and nuikit plugins enabled, Claude's commit trailer off (GIT-2)
```

## Changing nuikit

- The public API is every module-level name without a leading underscore in the seven modules, and
  [docs/api.md](docs/api.md) lists all of them. Keep it stable: a rename or a changed signature is a breaking
  change, and until 1.0 a breaking change bumps the minor version (semver). A new public name gets a row there;
  `tests/test_docs.py` fails while the page and the code differ.
- A rule change edits `docs/guide.md`, the code and tests its *Check* names, and the skills that show the pattern,
  in the same commit. Keep the rule ID and never reuse a retired one.
- A change to what a skill template produces runs `make test`: `tests/test_plugin.py` renders the family templates
  into a package, registers it and runs the item's test template against it.
- `src/` passes pyright strict, `tests/` pyright standard; the floor is Python 3.12, so every module starts with
  `from __future__ import annotations` (TYP-3).

## Tests

`make setup` runs `uv sync` and installs the pre-commit and commit-msg hooks. `make test` runs the unit tests, and
`make check` runs what CI runs: ruff, the conventions checks, import layers, pyright and pytest.

```bash
make setup
make test
make check
```

Fakes, not mocks, and they live in `tests/conftest.py`: its `fake_wandb` fixture swaps `wandb` for an in-process
fake module. Each case covers a distinct behaviour, named as a sentence.

## Release

nuikit is installed from its git tags; it is not published to a package index. To release, set `version` in
`pyproject.toml`, run `uv lock`, and merge that. Once CI passes on `main`, tag the commit with the same version:
`git tag v0.2.0 && git push origin v0.2.0`. Projects move to it by changing the tag under `[tool.uv.sources]` in
their `pyproject.toml` and running `uv lock`.

## Deviations

- Tests sit at `tests/test_<module>.py`, not `tests/nuikit/test_<module>.py` (TST-4): with one package, the extra
  level would say nothing.

## Commits

Conventional Commits with the standard types (`feat fix docs refactor test build ci perf style chore revert`), an
optional scope, a lowercase imperative subject: one line, no articles, no body or trailers. Short-lived
`<type>/<slug>` branches, squash-merged; `make github` sets the repo up for that once. PR descriptions follow
`.github/pull_request_template.md`.
