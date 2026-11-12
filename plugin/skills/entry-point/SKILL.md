---
name: entry-point
description: Use when adding or rewiring a command in a project built on nuikit, the console script that validates the config, configures logging, seeds, starts the run directory, builds the objects and reports user errors. Also when deciding how a command reports a problem the user can fix.
paths:
  - "src/**/cli/*.py"
  - "src/**/config.py"
  - "configs/*.yaml"
  - "pyproject.toml"
---

# Wire an entry point

A command is one module, `src/<pkg>/cli/<command>.py`, registered as a console script. Its `main` is the composition
root: the only place objects are built and wired (ARC-3). Rules:
[docs/guide.md](https://github.com/nuinashco/nuikit/blob/main/docs/guide.md) CFG-1, ERR-1, ERR-2, LOG-1, RUN-1,
RUN-2; conventions ARC-3, ERR-3, ERR-4, LOG-2, LOG-4, DOC-1.

Hydra serves commands that take a config; a small utility without one is a `click` command, still under
`@cli_boundary`, like `cli/configs.py` in projects from nuinashco/rnd-template.

Pick the names, then fill every `<...>` in the templates next to this file. Drop `from __future__ import annotations`
when the project's `requires-python` is 3.14 or later (TYP-3).

| placeholder | is | example |
|---|---|---|
| `<pkg>` | the project's import package | `my_pkg` |
| `<cli>` | the prefix of its console scripts in `[project.scripts]`: the package name with dashes | `my-pkg` |
| `<command>`, `<Command>` | the command, snake_case and CapWords | `evaluate`, `Evaluate` |
| `<group>`, `<kind>`, `<Family>` | a family the command builds: its group, its default kind, its base class | `sampler`, `sobol`, `Sampler` |

## Steps

1. Schema: `<Command>Config(Schema)` in `src/<pkg>/config.py`, with the run fields its mirror needs (`run_name`,
   `seed`, `deterministic`, `log_level`, `log_format`: copy them from `MainConfig`; move them into a shared base
   schema only once a third command repeats them, ARC-6). List it in `GENERATED` as
   `ConfigFile("defaults/<command>.yaml", <Command>Config, groups=(...))`, naming the fields config groups provide.
2. Entry config, hand-written, `configs/<command>.yaml`:

   ```yaml
   # Entry config of `<cli>-<command>`: values set below change every run of this repo.
   # Every setting with its default: defaults/<command>.yaml (generated).
   defaults:
     - defaults/<command>@_here_
     - <group>: <kind>
     - hydra: default
     - _self_
   ```

3. `templates/command.py.tmpl` -> `src/<pkg>/cli/<command>.py`. Keep its order: `from_hydra` validates before anything
   runs and no `DictConfig` goes further (CFG-1); `configure_logging` once (LOG-1); `seed_everything` once, passing
   the returned `rng` down (RUN-2); build items with `<Family>Factory.from_config(cfg.<group>)` and check that inputs,
   kinds and credentials work before expensive work (ERR-4); `start_run` (RUN-1); then the work, with outputs written
   into `run_dir`. `@cli_boundary` sits below `@hydra.main`. To mirror a run to W&B, call
   `runs.mirror_to_wandb(cfg, run_dir, project=cfg.wandb_project, entity=cfg.wandb_entity)` after `start_run` when
   `cfg.tracker == "wandb"`; the project then depends on `nuikit[wandb]`.
4. Register it in `pyproject.toml`: `[project.scripts]` `<cli>-<command> = "<pkg>.cli.<command>:main"`, then
   `uv sync`. Add it to README's command table.
5. `make configs`; the invariant tests compose and validate the new entry config.
6. Test the logic in the domain modules it wires. A test of the command itself composes the config and calls `main`
   in process: `templates/test_command.py.tmpl` -> `tests/<pkg>/cli/test_<command>.py`.
7. `make check`.

## Errors and output

A problem the user can fix raises `nuikit.errors.UserError` or a subclass: `ConfigError` (exit 2) for config,
`DataError` (exit 3) for input data (ERR-1). The message is lowercase without a final period: what is wrong, `; `,
then the remedy naming a command or config key, and an unknown name lists the valid ones (ERR-3).

```python
raise DataError(f"no samples in {path}; run `<cli>-prepare` first")
```

A package with its own failures subclasses `UserError` once, with a docstring and its own exit code:

```python
class ProxyError(UserError):
    """Proxy cannot start or cannot reach its upstream."""

    exit_code = 4
```

`@cli_boundary` is the only broad catch (ERR-2): it prints `error: <message>` and exits with the code, and lets every
other exception keep its traceback as a bug. Events go to `log.info("snake_case_event", key=value)` (LOG-2); results
meant for the user go to stdout through `click.echo` (LOG-4).
