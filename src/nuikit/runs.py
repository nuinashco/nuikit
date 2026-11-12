"""Run directories: one per run, holding the resolved config and its provenance."""

from __future__ import annotations

import atexit
import json
import re
import subprocess
import sys
from collections.abc import Collection, Iterator, Mapping, Sequence, Set
from datetime import UTC, datetime
from pathlib import Path
from typing import NewType, TypeAliasType, cast, get_args, get_origin

import structlog
from omegaconf import OmegaConf
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    RootModel,
    Secret,
    SecretBytes,
    SecretStr,
)
from pydantic.fields import FieldInfo

from nuikit.config import Schema
from nuikit.errors import ConfigError

log = structlog.stdlib.get_logger()

type _Json = dict[str, _Json] | list[_Json] | str | float | bool | None

_MASK = "**********"  # What pydantic writes for a secret, as config.yaml shows it.
_SECRET_TYPES = (Secret, SecretStr, SecretBytes)
# OmegaConf reads `${` as the start of an interpolation and the backslashes before it
# as escapes, and `???` after nothing but backslashes as a missing value.
_INTERPOLATION = re.compile(r"(\\*)\$\{")
_MISSING = re.compile(r"\\*\?\?\?")
# Keys of Hydra overrides (OverrideLexer.g4, VALUE_PATH): `a[b]` is another spelling
# of `a.b`, and a backslash keeps the `.`, `[`, `]` or `=` after it inside a segment.
_KEY_END = re.compile(r"(?<!\\)=")
_KEY_SEGMENT = re.compile(r"\[((?:\\[.\[\]=]|[^\]])*)\]|((?:\\[.\[\]=]|[^.\[])+)")
_KEY_ESCAPE = re.compile(r"\\([.\[\]=])")
_NO_COMMIT = "(initial)"  # What `git status` prints for HEAD before the first commit.


def start_run(
    config: Schema, *, name: str, runs_dir: Path, repo: Path | None = None
) -> Path:
    """Create `runs_dir/name/` with config.yaml and run.json; return the directory.

    config.yaml is the resolved config. A literal `${` or `???` in a string is
    escaped there, so that loading the file gives the text that ran, and a set is a
    list sorted by the JSON text of its items, the same in every run of one config.

    Only fields typed `SecretStr`, `SecretBytes` or `Secret[...]` are masked, there
    and in the command line that run.json records, where the value of each
    `key=value` that gives one is masked, by its name or an alias, except
    `~key=value` that deletes a value containing a schema with a secret. A token in a
    plain `str`, a URL that carries a password or a header in a plain dict is
    written as it is.

    run.json also records the commit and the dirty flag of the checkout at `repo`,
    the working directory when None, as they are before the directory is created.
    Untracked files count as dirty. Both are null without git and outside a
    checkout; when git fails for another reason they are null and a warning is logged.

    A `name` that leaves `runs_dir`, names it itself, or whose directory exists, is a
    ConfigError.
    """
    run_dir = runs_dir / name
    if not run_dir.resolve().is_relative_to(runs_dir.resolve()):
        raise ConfigError(
            f"run name {name} leaves {runs_dir}; pass a run_name that stays inside it"
        )
    if run_dir.resolve() == runs_dir.resolve():
        raise ConfigError(f"run name {name!r} names {runs_dir} itself; pass a run_name")
    dumped = _ordered(config, config.model_dump(mode="json"))
    snapshot = OmegaConf.to_yaml(_escaped(dumped))
    provenance = json.dumps(_provenance(config, repo), indent=2, ensure_ascii=False)
    try:
        run_dir.mkdir(parents=True)
    except FileExistsError as e:
        raise ConfigError(
            f"run directory {run_dir} exists; pass another run_name, in a sweep one "
            "per job such as 'run_name=sweep_${hydra:job.num}'"
        ) from e
    (run_dir / "config.yaml").write_text(snapshot, encoding="utf-8")
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

    The config is masked as config.yaml is: only fields typed `SecretStr`,
    `SecretBytes` or `Secret[...]`. `entity` is the W&B team or user to log to, None
    the login's default. `job_type`, `group` and `tags` let the W&B table filter and
    group runs; `system_stats` False drops the CPU, memory and GPU charts. The run
    finishes when the process exits. W&B records the command line as typed: a secret
    given there is not masked.
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


def _ordered(value: object, dumped: _Json) -> _Json:
    """Return `dumped`, the JSON form of `value`, with each list that was a set sorted.

    A set is dumped in the order of its hashes, which changes from one process to the
    next; sorted by the JSON text of its items, it is written the same every time.
    """
    held: list[object]
    if isinstance(value, RootModel):
        return _ordered(cast(RootModel[object], value).root, dumped)
    if isinstance(dumped, dict) and isinstance(value, BaseModel):
        names = _dumped_names(type(value))
        held = [getattr(value, names.get(key, key), None) for key in dumped]
    elif isinstance(dumped, dict) and isinstance(value, Mapping):
        held = list(cast(Mapping[object, object], value).values())
    elif isinstance(dumped, list) and isinstance(value, (Set, Sequence)):
        held = list(cast(Collection[object], value))
    else:
        return dumped
    if len(held) != len(dumped):  # A serializer the schema defines reshaped it.
        return dumped
    if isinstance(dumped, dict):
        pairs = zip(held, dumped.items(), strict=True)
        return {name: _ordered(inner, item) for inner, (name, item) in pairs}
    items = [_ordered(inner, item) for inner, item in zip(held, dumped, strict=True)]
    if not isinstance(value, Set):
        return items
    return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False))


def _dumped_names(model: type[BaseModel]) -> dict[str, str]:
    """Map each key that `model` is dumped under to the name of its field."""
    if not model.model_config.get("serialize_by_alias"):
        return {}
    fields = model.model_fields.items()
    return {info.serialization_alias or name: name for name, info in fields}


def _escaped(dumped: _Json) -> _Json:
    """Return `dumped` with `${` and `???` escaped in each string, for OmegaConf."""
    if isinstance(dumped, str):
        if _MISSING.fullmatch(dumped):
            return "\\" + dumped
        return _INTERPOLATION.sub(lambda found: found[1] * 2 + "\\${", dumped)
    if isinstance(dumped, dict):
        return {name: _escaped(item) for name, item in dumped.items()}
    if isinstance(dumped, list):
        return [_escaped(item) for item in dumped]
    return dumped


def _provenance(config: Schema, repo: Path | None) -> dict[str, object]:
    git_sha, dirty = _git_state(repo)
    return {
        "git_sha": git_sha,
        "dirty": dirty,
        "argv": _masked(sys.argv, config),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _git_state(repo: Path | None) -> tuple[str | None, bool | None]:
    """Return the commit and the dirty flag of the checkout at `repo`, or two Nones.

    Without git and outside a checkout nothing is logged; any other failure of git
    is logged once, with the first line of its error.
    """
    status = ("status", "--porcelain=v2", "--branch", "--untracked-files=normal")
    try:
        result = subprocess.run(
            ["git", *status],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            cwd=repo,
        )
    except OSError:  # `git` is not installed, or `repo` is not a directory.
        return None, None
    if result.returncode != 0:
        try:
            where = (repo or Path.cwd()).resolve()
        except OSError:  # The working directory was deleted.
            return None, None
        # Git words "not a git repository" in the user's language, and says it of a
        # broken repository too, so a `.git` entry tells a checkout from the rest.
        if _inside_checkout(where):
            error = result.stderr.strip().partition("\n")[0]
            log.warning("git_state_unreadable", repo=str(where), error=error)
        return None, None
    lines = result.stdout.splitlines()
    heads = (line.split()[2] for line in lines if line.startswith("# branch.oid "))
    head = next(heads, _NO_COMMIT)
    dirty = any(not line.startswith("#") for line in lines)
    return (None if head == _NO_COMMIT else head), dirty


def _inside_checkout(folder: Path) -> bool:
    entries = (above / ".git" for above in (folder, *folder.parents))
    return any(entry.exists(follow_symlinks=False) for entry in entries)


def _masked(argv: Sequence[str], config: Schema) -> list[str]:
    """Return `argv` with the value of each `key=value` that gives a secret masked.

    A key gives a secret when, after Hydra's leading `+`, `++` or `~`, one of its
    segments names a field that holds one, by its name or an alias, whether the key
    is spelled with dots or with Hydra's brackets. So does a key above the path of a
    secret whose value is a mapping.
    """
    secrets = list(_secrets(config))
    paths = {path for path, _ in secrets}
    fields = {field for _, field in secrets}
    masked: list[str] = []
    for arg in argv:
        typed_key, *rest = _KEY_END.split(arg, maxsplit=1)
        segments = _segments(typed_key.lstrip("+~"))
        key = ".".join(segments)
        gives_secret = not fields.isdisjoint(segments) or (
            "{" in "".join(rest) and any(path.startswith(f"{key}.") for path in paths)
        )
        masked.append(f"{typed_key}={_MASK}" if rest and gives_secret else arg)
    return masked


def _segments(key: str) -> list[str]:
    """Return the segments of a Hydra key: `a.b[c]` and `a.b.c` give the same three."""
    found = cast(list[tuple[str, str]], _KEY_SEGMENT.findall(key))
    return [_KEY_ESCAPE.sub(r"\1", bracketed or dotted) for bracketed, dotted in found]


def _secrets(
    value: object, *, path: tuple[str, ...] = (), field: str = ""
) -> Iterator[tuple[str, str]]:
    """Yield the dotted path of each secret at or below `value`, and its field's key.

    The field is the innermost schema field on the path: the one that holds the secret,
    directly or inside mappings and sequences. A field given by its name or by an
    alias yields a path for each, and the first segment of that key as the field's.
    A field typed for a secret counts whatever it holds: the config no longer holds
    what `~key=value` deleted.
    """
    if isinstance(value, _SECRET_TYPES):
        yield ".".join(path), field
    elif isinstance(value, RootModel):
        # Hydra's keys skip `root`: the model is written as what it holds.
        root = cast(RootModel[object], value).root
        yield from _secrets(root, path=path, field=field)
    elif isinstance(value, BaseModel):
        yield from _field_secrets(value, path=path)
    elif isinstance(value, Mapping):
        for key, item in cast(Mapping[object, object], value).items():
            yield from _secrets(item, path=(*path, str(key)), field=field)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(cast(Sequence[object], value)):
            yield from _secrets(item, path=(*path, str(index)), field=field)


def _field_secrets(
    model: BaseModel, *, path: tuple[str, ...]
) -> Iterator[tuple[str, str]]:
    """Yield what `_secrets` does for each field of `model`, under each of its keys."""
    for name, info in type(model).model_fields.items():
        # Walked once for all keys: a walk per key would double at every level.
        below = list(_secrets(getattr(model, name)))
        for key in _keys(name, info):
            prefix = (*path, *key)
            if _typed_secret(info.annotation):
                yield ".".join(prefix), key[0]
            for inner, field in below:
                yield ".".join((*prefix, inner) if inner else prefix), field or key[0]


def _keys(name: str, info: FieldInfo) -> list[tuple[str, ...]]:
    """Return the segments of each key a config may give a field by.

    Schema validates by alias, so an alias is the key Hydra composes for the field;
    a schema that validates by name as well takes the name too.
    """
    alias = info.validation_alias
    choices = alias.choices if isinstance(alias, AliasChoices) else [alias]
    paths = (c.path if isinstance(c, AliasPath) else [c] for c in choices if c)
    return [(name,), *(tuple(map(str, path)) for path in paths)]


def _typed_secret(annotation: object, *, seen: tuple[object, ...] = ()) -> bool:
    """Tell whether `annotation` names a secret type, in a container or alias too."""
    if isinstance(annotation, TypeAliasType):
        if annotation in seen:  # A `type` alias may name itself.
            return False
        return _typed_secret(annotation.__value__, seen=(*seen, annotation))
    if isinstance(annotation, NewType):
        return _typed_secret(annotation.__supertype__, seen=seen)
    if isinstance(annotation, type):
        return issubclass(annotation, _SECRET_TYPES)
    origin = get_origin(annotation)
    parts = (origin, *get_args(annotation))
    return origin is not None and any(_typed_secret(part, seen=seen) for part in parts)
