# nuikit

The machinery that config-driven Python projects share: strict config schemas validated from Hydra, YAML generated
from them, families of interchangeable items chosen by `kind`, user errors with exit codes, structured logging, run
directories with provenance, and seeding. Projects from
[nuinashco/rnd-template](https://github.com/nuinashco/rnd-template) are built on it.

The rules for code that uses it are in
[docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md); the general conventions are in
[nuinashco/conventions](https://github.com/nuinashco/conventions). Changing nuikit itself:
[CONTRIBUTING.md](https://github.com/nuinashco/nuikit/blob/main/CONTRIBUTING.md).

## Install

Python 3.12 or later.

```bash
uv add nuikit "hydra-core>=1.4.0rc1"   # or nuikit[wandb] to mirror runs to Weights & Biases
uv add "nuikit @ git+https://github.com/nuinashco/nuikit@v0.1.0"   # a tag, straight from GitHub
pip install nuikit
```

nuikit needs `hydra-core>=1.4.0rc1`, a pre-release, because 1.3.x crashes on Python 3.14. pip accepts it through
nuikit's own requirement. uv takes a pre-release only when your project names it, or when nuikit comes from a git or
path source, so list `hydra-core>=1.4.0rc1` in your own dependencies, as projects from the rnd template do. torch is
optional: `seed_everything` seeds it when it is installed.

## Modules

| module | gives |
|---|---|
| `nuikit.config` | `Schema`, a pydantic base that rejects unknown keys and freezes values; `Schema.from_hydra(cfg)` validates a composed Hydra config and raises one `ConfigError` naming every bad field |
| `nuikit.configgen` | `ConfigFile`, `render`, `stale`, `write`: the YAML mirror of a schema, every field with its default and description; `HEADER`, `PACKAGE`, `GROUPS`, `REQUIRED`: the comment lines and `???` marker it writes |
| `nuikit.registry` | `KindConfig`, `Configurable`, `ConfigurableFactory` (over `BaseFactory`, a registry keyed by `kind`): families whose items register by `kind` and build from config; `import_submodules`, `import_tree`, `families`, `config_files`, `kind_path`, `kind_package` for discovery and generated configs |
| `nuikit.errors` | `UserError`, `ConfigError` (exit 2), `DataError` (exit 3), and `@cli_boundary`, which prints `error: <message>` and exits with the code; `describe` and `first_line` word pydantic and OmegaConf errors the way it prints them |
| `nuikit.logging` | `configure_logging(level=..., fmt=...)`: structlog over stdlib, console on a terminal, JSON elsewhere; `LogLevel` and `LogFormat`, the literal types of `level` and `fmt`, for config fields |
| `nuikit.runs` | `start_run`: `runs/<name>/` with `config.yaml` (secrets masked) and `run.json` (git SHA, dirty flag, argv, start time); `mirror_to_wandb`, with the `wandb` extra |
| `nuikit.seeding` | `seed_everything(seed, deterministic=...)`: seeds Python, NumPy and torch, and returns the `np.random.Generator` to pass around |

A family in one file (a project splits it into `base.py` and `items/`, FAM-1):

```python
from abc import ABC, abstractmethod
from typing import Any

from attrs import define

from nuikit.registry import Configurable, ConfigurableFactory, KindConfig


class ShapeConfig(KindConfig):
    """Settings every shape kind shares."""


@define
class Shape[C: ShapeConfig](Configurable[C], ABC):
    """Plane figure."""

    @abstractmethod
    def area(self) -> float: ...


class ShapeFactory(ConfigurableFactory[Shape[Any]]):
    """Registry of shape kinds; `shape=<kind>` selects one."""

    config_group = "shape"


class SquareShapeConfig(ShapeConfig):
    """Settings of the square shape."""

    side_m: float = 1.0


@ShapeFactory.register("square")  # Outermost: attrs replaces the class below it.
@define
class SquareShape(Shape[SquareShapeConfig]):
    """Axis-aligned square."""

    def area(self) -> float:
        return self.config.side_m**2


ShapeFactory.from_config({"kind": "square", "side_m": 2}).area()  # 4.0
```

## Claude Code plugin

`plugin/` is the `nuikit` plugin: skills that write code the way
[docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md) asks.

| skill | use it to |
|---|---|
| `add-family` | create a family: `base.py` with base, config and factory, `items/`, the import layer, configs and tests |
| `add-family-item` | add a kind to a family |
| `add-config-field` | add a setting: which schema owns it, its default and description, `make configs`, where to change it |
| `entry-point` | wire a command: validate, log, seed, start the run, build items, report user errors |

It is published through the `nuinashco` marketplace in the conventions repo. Enable it once per machine, ideally in
user settings; projects from the rnd template already enable it in `.claude/settings.json`.

```text
/plugin marketplace add nuinashco/conventions
/plugin install nuikit@nuinashco
```

## Release

Versions follow semver. The public API is every module-level name without a leading underscore in the seven modules
above, all of them listed in the table. To release, set `version` in `pyproject.toml`, run `uv lock`, commit, then
push the tag:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

`.github/workflows/release.yml` checks that the tag matches `version`, builds with `uv build` and publishes to PyPI
through trusted publishing, so no API token is stored anywhere. One-time setup before the first tag:

1. On PyPI, under Account settings > Publishing, add a pending trusted publisher: PyPI project name `nuikit`, owner
   `nuinashco`, repository `nuikit`, workflow `release.yml`, environment `pypi`. The first release creates the
   project.
2. On GitHub, under the repo's Settings > Environments, create the environment `pypi`. Limiting its deployment refs
   to tags `v*` keeps other refs from publishing.
