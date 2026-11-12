# nuikit

The parts that config-driven Python projects share, as one small library: config schemas checked before anything
runs, YAML files generated from them, interchangeable items chosen by a `kind` key, errors with exit codes, logging,
run folders and seeding.

It is for projects that compose their config with [Hydra](https://hydra.cc/). Starting a new one? Use
[rnd-template](https://github.com/nuinashco/rnd-template), which sets nuikit up for you.

## Install

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or later. Inside a uv project (`uv init` makes one), add
Hydra first, then nuikit, pinned to a release tag:

```bash
uv add "hydra-core>=1.4.0rc1"
uv add git+https://github.com/nuinashco/nuikit --tag v0.1.0
```

Hydra goes first, with its pre-release named: nuikit needs OmegaConf 2.4, which Hydra 1.3 does not accept, so a
project on Hydra 1.3 must move to the 1.4 pre-release before nuikit can be added. To mirror runs to Weights & Biases,
add `--extra wandb` to the second command. torch is optional: `seed_everything` seeds it when it is installed.

To move to a newer release, change the tag under `[tool.uv.sources]` in your `pyproject.toml` and run `uv lock`.

## Use

Declare the settings as a schema and wrap the entry point, so that a mistake in the config prints one clear message:

```python
# train.py
from omegaconf import OmegaConf
from pydantic import Field

from nuikit.config import Schema
from nuikit.errors import cli_boundary


class TrainConfig(Schema):
    """Settings of one training run."""

    steps: int = Field(default=100, gt=0)
    lr: float = 3e-4


@cli_boundary
def main() -> None:
    cfg = TrainConfig.from_hydra(OmegaConf.from_cli())
    print(cfg)


main()
```

Here the config comes from the command line; in a project it is the one Hydra composed.

```console
$ uv run python train.py steps=500
steps=500 lr=0.0003
$ uv run python train.py steps=0 lrr=1
error: invalid TrainConfig:
  steps: Input should be greater than 0
  lrr: Extra inputs are not permitted
$ echo $?
2
```

## What is in it

| module | what it gives you |
|---|---|
| `nuikit.config` | `Schema`: a pydantic model that rejects unknown keys, is read-only and validates a Hydra config in one call. |
| `nuikit.configgen` | The YAML file of a schema, with every default and description, and a check that it is up to date. |
| `nuikit.registry` | Families: items that register under a `kind` and are built from the config that names it. |
| `nuikit.errors` | `UserError` with an exit code, and `@cli_boundary`, which prints `error: <message>` instead of a traceback. |
| `nuikit.logging` | `configure_logging`: readable lines in a terminal, JSON everywhere else. |
| `nuikit.runs` | `start_run`: a folder per run, with its config and the git commit it ran from. |
| `nuikit.seeding` | `seed_everything`: seeds Python, NumPy and torch, and returns the generator to pass around. |

[docs/api.md](docs/api.md) lists every public name and shows a family in one file.
[docs/guide.md](docs/guide.md) holds the rules for code that uses them.

## Claude Code plugin

The `nuikit` plugin gives Claude skills that write this code the way the guide asks. Install it once per machine;
projects from rnd-template already turn it on.

```text
/plugin marketplace add nuinashco/conventions
/plugin install nuikit@nuinashco
```

| skill | use it to |
|---|---|
| `add-family` | create a family: base class, config, factory, items, configs and tests |
| `add-family-item` | add a kind to a family |
| `add-config-field` | add a setting, with its default and description |
| `entry-point` | wire a command: validate, log, seed, start the run, report user errors |

## Related repos

- [conventions](https://github.com/nuinashco/conventions): the general rules, their checks and the plugin marketplace.
- [rnd-template](https://github.com/nuinashco/rnd-template): the template that starts a project on nuikit.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the architecture, the layout, tests and releases.

## License

[MIT](LICENSE)
