"""Run directories: one per run, holding the resolved config and its provenance."""

from __future__ import annotations

import atexit
import json
import subprocess
import sys
from collections.abc import Collection, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, get_args

from omegaconf import OmegaConf
from pydantic import BaseModel, SecretStr

from nuikit.config import Schema
from nuikit.errors import ConfigError

_MASK = "**********"  # What pydantic writes for a secret, as config.yaml shows it.


def start_run(config: Schema, *, name: str, runs_dir: Path) -> Path:
    """Create `runs_dir/name/` with config.yaml and run.json, secrets masked in both.

    run.json records the command line, with the value of each `key=value` that gives
    a secret masked. A `name` that leaves `runs_dir`, or whose directory exists, is a
    ConfigError.
    """
    run_dir = runs_dir / name
    if not run_dir.resolve().is_relative_to(runs_dir.resolve()):
        raise ConfigError(
            f"run name {name} leaves {runs_dir}; pass a relative run_name without `..`"
        )
    try:
        run_dir.mkdir(parents=True)
    except FileExistsError as e:
        raise ConfigError(
            f"run directory {run_dir} exists; pass another run_name"
        ) from e
    snapshot = OmegaConf.to_yaml(config.model_dump(mode="json"))
    (run_dir / "config.yaml").write_text(snapshot, encoding="utf-8")
    provenance = json.dumps(_provenance(run_dir, config), indent=2, ensure_ascii=False)
    (run_dir / "run.json").write_text(provenance + "\n", encoding="utf-8")
    return run_dir


def mirror_to_wandb(
    config: Schema,
    run_dir: Path,
    *,
    project: str,
    entity: str | None = None,
    job_type: str | None = None,
    group: str | None = None,
    tags: Sequence[str] = (),
    exclude: Collection[str] = (),
    system_stats: bool = True,
) -> None:
    """Start a W&B run named after `run_dir`, with its config but the `exclude` keys.

    `entity` is the W&B team or user to log to, None the login's default.
    `job_type`, `group` and `tags` let the W&B table filter and group runs;
    `system_stats` False drops the CPU, memory and GPU charts. The run finishes when
    the process exits. W&B records the command line as typed: a secret given there is
    not masked.
    """
    import wandb

    run = wandb.init(
        project=project,
        entity=entity,
        name=run_dir.name,
        dir=run_dir,
        job_type=job_type,
        group=group,
        tags=list(tags),
        config={
            key: value
            for key, value in config.model_dump(mode="json").items()
            if key not in exclude
        },
        settings=wandb.Settings(x_disable_stats=not system_stats),
    )
    # Left to W&B's own exit hook, teardown abandons a pending message and logs an
    # error; hooks run last-registered first, so this one runs before it.
    atexit.register(run.finish)


def _provenance(run_dir: Path, config: Schema) -> dict[str, object]:
    status = _git("status", "--porcelain", cwd=run_dir)
    return {
        "git_sha": _git("rev-parse", "HEAD", cwd=run_dir),
        "dirty": None if status is None else bool(status),  # None: not a checkout.
        "argv": _masked(sys.argv, config),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _masked(argv: Sequence[str], config: Schema) -> list[str]:
    """Return `argv` with the value of each `key=value` that gives a secret masked.

    A key gives a secret when, after Hydra's leading `+`, `++` or `~`, it is the dotted
    path of a secret in `config` or ends in the name of a field that holds one. So
    does a key above such a path whose value is a mapping.
    """
    secrets = list(_secrets(config))
    paths = {path for path, _ in secrets}
    fields = {field for _, field in secrets}
    masked: list[str] = []
    for arg in argv:
        typed_key, equals, value = arg.partition("=")
        key = typed_key.lstrip("+~")
        gives_secret = (
            key in paths
            or key.rpartition(".")[2] in fields
            or ("{" in value and any(path.startswith(f"{key}.") for path in paths))
        )
        masked.append(f"{typed_key}={_MASK}" if equals and gives_secret else arg)
    return masked


def _secrets(
    value: object, *, path: tuple[str, ...] = (), field: str = ""
) -> Iterator[tuple[str, str]]:
    """Yield the dotted path of each secret at or below `value`, and its field's name.

    The field is the innermost schema field on the path: the one that holds the secret,
    directly or inside mappings and sequences. A field typed for a secret counts while
    it is None too: `~key=value` deletes a setting only when `value` is what it held.
    """
    if isinstance(value, SecretStr):
        yield ".".join(path), field
    elif isinstance(value, BaseModel):
        for name, info in type(value).model_fields.items():
            item = getattr(value, name)
            if item is None and _typed_secret(info.annotation):
                yield ".".join((*path, name)), name
            else:
                yield from _secrets(item, path=(*path, name), field=name)
    elif isinstance(value, Mapping):
        for key, item in cast(Mapping[object, object], value).items():
            yield from _secrets(item, path=(*path, str(key)), field=field)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(cast(Sequence[object], value)):
            yield from _secrets(item, path=(*path, str(index)), field=field)


def _typed_secret(annotation: object) -> bool:
    if args := get_args(annotation):
        return any(map(_typed_secret, args))
    return isinstance(annotation, type) and issubclass(annotation, SecretStr)


def _git(*args: str, cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False, cwd=cwd
        )
    except OSError:  # `git` is not installed.
        return None
    return result.stdout.strip() if result.returncode == 0 else None
