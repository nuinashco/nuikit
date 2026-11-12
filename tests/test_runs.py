"""A run directory records config, secrets masked, and provenance; W&B mirrors it."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NewType

import pytest
from omegaconf import DictConfig, OmegaConf
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    Secret,
    SecretBytes,
    SecretStr,
)
from pydantic_core import PydanticSerializationError
from structlog.testing import capture_logs

from nuikit.config import Schema
from nuikit.errors import ConfigError
from nuikit.runs import mirror_to_wandb, start_run

type Token = SecretStr
type Tree = dict[str, Tree] | str
Pin = NewType("Pin", SecretStr)


class Run(Schema):
    """Config with a secret."""

    seed: int = 1
    api_key: SecretStr = SecretStr("hunter2")


class Endpoint(Schema):
    """Nested config with a secret of its own."""

    password: SecretStr


class Replica(Schema):
    """Config held in a mapping of sequences, with a secret of its own."""

    passphrase: SecretStr


class Headers(RootModel[dict[str, SecretStr]]):
    """Headers as a model of their own."""


class Stack(Schema):
    """Config with secrets of every type: set, unset, nested, in containers, renamed."""

    api_key: SecretStr
    spare_key: SecretStr | None = None
    alias_key: Token
    spare_alias: Token | None = None
    spare_pin: Pin | None = None
    signing_key: SecretBytes
    passcode: Secret[int]
    endpoint: Endpoint
    replicas: dict[str, list[Replica]]
    headers: dict[str, SecretStr]
    tokens: list[SecretStr]
    spare_tokens: tuple[SecretStr, ...] = ()
    groups: dict[str, list[SecretStr]]
    labels: Tree = "none"
    keyed: SecretStr | None = Field(None, alias="apiKey")
    chosen: SecretStr | None = Field(
        None, validation_alias=AliasChoices("authKey", AliasPath("auth", 0))
    )
    vaulted: SecretStr | None = Field(None, validation_alias=AliasPath("vault", "key"))
    wrapped: Headers = Headers({"bearer": SecretStr("from-env")})
    seed: int = 1


STACK = Stack.model_validate(
    {
        "api_key": "from-env",
        "alias_key": "from-env",
        "signing_key": "from-env",
        "passcode": 1234,
        "endpoint": {"password": "from-env"},
        "replicas": {"eu": [{"passphrase": "from-env"}]},
        "headers": {"authorization": "from-env"},
        "tokens": ["from-env", "from-env"],
        "groups": {"team": ["from-env"]},
    }
)


class Service(Schema):
    """Config with credentials typed as secrets, and one left in plain text."""

    url: SecretStr
    headers: dict[str, SecretStr]
    note: str


class Prompt(Schema):
    """Config with free text."""

    text: str


class Opaque(Schema):
    """Config with a value that has no JSON form."""

    handle: Any


class Stage(Schema):
    """Nested config with a set."""

    ids: set[int]


class Labels(RootModel[frozenset[str]]):
    """Set that is a model of its own."""


class Owner(BaseModel):
    """Nested model written under its aliases."""

    model_config = ConfigDict(serialize_by_alias=True)

    team_tags: frozenset[str] = Field(alias="teamTags")


class Pipeline(Schema):
    """Config with sets: of text, in nested models and in another set."""

    tags: frozenset[str]
    stages: dict[str, list[Stage]]
    pairs: frozenset[frozenset[str]]
    labels: Labels
    owner: Owner


def git(*args: str, cwd: Path) -> str:
    """Run git in `cwd` as a fixed author and return what it prints."""
    author = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")
    done = subprocess.run(
        ["git", *author, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def git_state(run_dir: Path) -> tuple[str | None, bool | None]:
    provenance = json.loads((run_dir / "run.json").read_text())
    return provenance["git_sha"], provenance["dirty"]


@pytest.fixture
def git_env(monkeypatch) -> None:
    """Let git read no settings but a repository's own, and find it from its folder."""
    for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        monkeypatch.setenv(name, os.devnull)
    # Inside a git hook these point every git command at the repository it runs for.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def checkout(tmp_path, git_env) -> Path:
    """Make a git checkout with one commit, under no git settings but its own."""
    root = tmp_path / "code"
    root.mkdir()
    git("init", "--quiet", cwd=root)
    (root / "train.py").write_text("print('code')\n")
    git("add", "train.py", cwd=root)
    git("commit", "--quiet", "--message", "init", cwd=root)
    return root


def test_start_run_writes_masked_config_and_provenance(tmp_path):
    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path)

    config = OmegaConf.load(run_dir / "config.yaml")
    provenance = json.loads((run_dir / "run.json").read_text())
    assert (config.seed, config.api_key) == (1, "**********")
    assert set(provenance) == {"git_sha", "dirty", "argv", "started_at"}


def test_only_fields_typed_as_secrets_are_masked_in_config_yaml_and_for_wandb(
    tmp_path, monkeypatch, fake_wandb
):
    monkeypatch.setattr(atexit, "register", lambda finish: None)
    service = Service.model_validate(
        {
            "url": "postgresql://user:hunter2@db/x",
            "headers": {"authorization": "Bearer hunter2"},
            "note": "token hunter2",
        }
    )

    run_dir = start_run(service, name="r1", runs_dir=tmp_path)
    mirror_to_wandb(service, run_dir, project="p")

    written = OmegaConf.to_container(OmegaConf.load(run_dir / "config.yaml"))
    [run] = fake_wandb.runs
    assert (
        written
        == run.init["config"]
        == {
            "url": "**********",
            "headers": {"authorization": "**********"},
            "note": "token hunter2",
        }
    )


@pytest.mark.parametrize(
    "text",
    ["print ${HOME}", "unbalanced ${", r"C:\${drive}", r"a\\${b}", "???", r"\???"],
    ids=[
        "interpolation",
        "unclosed-interpolation",
        "backslash-before-interpolation",
        "two-backslashes-before-interpolation",
        "missing-marker",
        "backslash-before-missing-marker",
    ],
)
def test_config_yaml_loads_back_to_the_text_that_ran(tmp_path, text):
    config = Prompt(text=text)

    run_dir = start_run(config, name="r1", runs_dir=tmp_path)

    loaded = OmegaConf.load(run_dir / "config.yaml")
    assert isinstance(loaded, DictConfig)
    assert Prompt.from_hydra(loaded) == config


def test_config_that_cannot_be_written_leaves_no_run_directory_behind(tmp_path):
    with pytest.raises(PydanticSerializationError):
        start_run(Opaque(handle=object()), name="r1", runs_dir=tmp_path)

    assert not (tmp_path / "r1").exists()


def test_sets_are_written_sorted_by_the_json_text_of_their_items_at_any_depth(
    tmp_path,
):
    pipeline = Pipeline(
        tags=frozenset("hgfedcba"),
        stages={"fit": [Stage(ids={9, 10, 100})]},
        pairs=frozenset({frozenset("dc"), frozenset("ba")}),
        labels=Labels(frozenset("zyxwvuts")),
        owner=Owner(teamTags=frozenset("rqponmlk")),
    )

    run_dir = start_run(pipeline, name="r1", runs_dir=tmp_path)

    assert OmegaConf.to_container(OmegaConf.load(run_dir / "config.yaml")) == {
        "tags": ["a", "b", "c", "d", "e", "f", "g", "h"],
        "stages": {"fit": [{"ids": [10, 100, 9]}]},
        "pairs": [["a", "b"], ["c", "d"]],
        "labels": ["s", "t", "u", "v", "w", "x", "y", "z"],
        "owner": {"teamTags": ["k", "l", "m", "n", "o", "p", "q", "r"]},
    }


@pytest.mark.parametrize(
    ("typed", "recorded"),
    [
        pytest.param("api_key=sk-1", "api_key=**********", id="field"),
        pytest.param("++api_key=sk-1", "++api_key=**********", id="forced"),
        pytest.param("~spare_key=sk-1", "~spare_key=**********", id="deleted"),
        pytest.param("alias_key=sk-1", "alias_key=**********", id="type-alias"),
        pytest.param(
            "endpoint.password=sk-1", "endpoint.password=**********", id="nested-schema"
        ),
        pytest.param(
            "replicas.eu.0.passphrase=sk-1",
            "replicas.eu.0.passphrase=**********",
            id="schema-in-containers",
        ),
        pytest.param(
            "headers.authorization=sk-1",
            "headers.authorization=**********",
            id="mapping",
        ),
        pytest.param("tokens.1=sk-1", "tokens.1=**********", id="sequence"),
        pytest.param("tokens=[sk-1,sk-2]", "tokens=**********", id="whole-sequence"),
        pytest.param(
            "~spare_tokens=[sk-1]", "~spare_tokens=**********", id="deleted-sequence"
        ),
        pytest.param(
            "groups.team=[sk-1,sk-2]",
            "groups.team=**********",
            id="sequence-in-mapping",
        ),
        pytest.param(
            "~groups.gone=[sk-1]", "~groups.gone=**********", id="deleted-item"
        ),
        pytest.param(
            "fallback.password=sk-1", "fallback.password=**********", id="same-name"
        ),
        pytest.param(
            "endpoint={password: sk-1}",
            "endpoint=**********",
            id="mapping-above-secret",
        ),
        pytest.param("endpoint=remote", "endpoint=remote", id="group-above-secret"),
        pytest.param("tokens[1]=sk-1", "tokens[1]=**********", id="bracketed-sequence"),
        pytest.param(
            "headers[authorization]=sk-1",
            "headers[authorization]=**********",
            id="bracketed-mapping",
        ),
        pytest.param(
            "endpoint[password]=sk-1",
            "endpoint[password]=**********",
            id="bracketed-nested-schema",
        ),
        pytest.param(
            "replicas[eu]=[{passphrase: sk-1}]",
            "replicas[eu]=**********",
            id="bracketed-mapping-above-secret",
        ),
        pytest.param(
            r"replicas.a\=b.0.passphrase=sk-1",
            r"replicas.a\=b.0.passphrase=**********",
            id="escaped-equals-in-key",
        ),
        pytest.param(
            "~spare_alias=sk-1", "~spare_alias=**********", id="deleted-type-alias"
        ),
        pytest.param("~spare_pin=sk-1", "~spare_pin=**********", id="deleted-newtype"),
        pytest.param("signing_key=sk-1", "signing_key=**********", id="secret-bytes"),
        pytest.param("passcode=4321", "passcode=**********", id="secret-of-a-number"),
        pytest.param("apiKey=sk-1", "apiKey=**********", id="field-alias"),
        pytest.param("keyed=sk-1", "keyed=**********", id="name-of-aliased-field"),
        pytest.param(
            "wrapped.bearer=sk-1", "wrapped.bearer=**********", id="root-model"
        ),
        pytest.param("authKey=sk-1", "authKey=**********", id="alias-choice"),
        pytest.param("auth=[sk-1]", "auth=**********", id="alias-path-choice"),
        pytest.param("vault.key=sk-1", "vault.key=**********", id="alias-path"),
        pytest.param("labels[team]=core", "labels[team]=core", id="bracketed-other"),
        pytest.param("seed=2", "seed=2", id="other-setting"),
        pytest.param("~api_key", "~api_key", id="no-value"),
    ],
)
def test_run_json_records_argv_with_the_value_of_each_secret_override_masked(
    tmp_path, monkeypatch, typed, recorded
):
    monkeypatch.setattr(sys, "argv", ["demo-run", typed])

    run_dir = start_run(STACK, name="r1", runs_dir=tmp_path)

    provenance = json.loads((run_dir / "run.json").read_text())
    assert (provenance["argv"], sys.argv) == (
        ["demo-run", recorded],
        ["demo-run", typed],
    )


def test_existing_run_directory_is_never_reused_and_the_error_says_what_a_sweep_needs(
    tmp_path,
):
    start_run(Run(), name="r1", runs_dir=tmp_path)

    with pytest.raises(ConfigError) as error:
        start_run(Run(), name="r1", runs_dir=tmp_path)

    assert str(error.value) == (
        f"run directory {tmp_path / 'r1'} exists; pass another run_name, in a sweep "
        "one per job such as 'run_name=sweep_${hydra:job.num}'"
    )


@pytest.mark.parametrize(
    "name", ["../escaped", "{outside}/escaped"], ids=["parent", "absolute"]
)
def test_run_name_that_leaves_the_runs_directory_is_refused(tmp_path, name):
    runs_dir = tmp_path / "runs"

    with pytest.raises(ConfigError, match="leaves"):
        start_run(Run(), name=name.format(outside=tmp_path), runs_dir=runs_dir)

    assert not (tmp_path / "escaped").exists()


def test_nested_run_name_stays_inside_the_runs_directory(tmp_path):
    run_dir = start_run(Run(), name="sweep/1", runs_dir=tmp_path)

    assert (run_dir, (run_dir / "run.json").is_file()) == (
        tmp_path / "sweep" / "1",
        True,
    )


@pytest.mark.parametrize(
    "runs_dir",
    ["disk/runs", "results/runs"],
    ids=["runs-outside-any-checkout", "runs-inside-another-repository"],
)
def test_run_json_describes_the_checkout_at_repo_wherever_the_runs_are(
    tmp_path, checkout, runs_dir
):
    results = tmp_path / "results"
    results.mkdir()
    git("init", "--quiet", cwd=results)
    git("commit", "--quiet", "--allow-empty", "--message", "results", cwd=results)

    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / runs_dir, repo=checkout)

    assert git_state(run_dir) == (git("rev-parse", "HEAD", cwd=checkout), False)


def test_checkout_is_the_working_directory_unless_repo_names_another(
    tmp_path, checkout, monkeypatch
):
    monkeypatch.chdir(checkout)

    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "disk" / "runs")

    assert git_state(run_dir) == (git("rev-parse", "HEAD", cwd=checkout), False)


def test_run_directory_inside_the_checkout_does_not_make_its_own_record_dirty(
    checkout, monkeypatch
):
    monkeypatch.chdir(checkout)

    run_dir = start_run(Run(), name="r1", runs_dir=checkout / "runs")

    assert git_state(run_dir) == (git("rev-parse", "HEAD", cwd=checkout), False)


@pytest.mark.parametrize(
    "changed", ["train.py", "notes.txt"], ids=["tracked-file-edited", "untracked-file"]
)
def test_edited_and_untracked_files_make_the_record_dirty(tmp_path, checkout, changed):
    git("config", "status.showUntrackedFiles", "no", cwd=checkout)
    (checkout / changed).write_text("changed\n")

    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs", repo=checkout)

    assert git_state(run_dir) == (git("rev-parse", "HEAD", cwd=checkout), True)


def test_checkout_before_its_first_commit_has_no_sha_and_logs_nothing(
    tmp_path, checkout
):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git("init", "--quiet", cwd=fresh)
    (fresh / "train.py").write_text("")

    with capture_logs() as logs:
        run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs", repo=fresh)

    assert (git_state(run_dir), logs) == ((None, True), [])


def test_outside_a_checkout_the_git_state_is_null_and_nothing_is_logged(
    tmp_path, git_env
):
    with capture_logs() as logs:
        run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs", repo=tmp_path)

    assert (git_state(run_dir), logs) == ((None, None), [])


def test_without_git_the_git_state_is_null_and_nothing_is_logged(
    tmp_path, checkout, monkeypatch
):
    monkeypatch.setenv("PATH", str(tmp_path))

    with capture_logs() as logs:
        run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs", repo=checkout)

    assert (git_state(run_dir), logs) == ((None, None), [])


def test_deleted_working_directory_gives_a_null_git_state(
    tmp_path, git_env, monkeypatch
):
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()

    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs")

    assert git_state(run_dir) == (None, None)


def test_git_failure_inside_a_checkout_is_logged_once_and_recorded_as_null(
    tmp_path, git_env
):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text("gitdir: nowhere\n")

    with capture_logs() as logs:
        run_dir = start_run(Run(), name="r1", runs_dir=tmp_path / "runs", repo=broken)

    [warning] = logs
    # Git words the error differently from one release to the next.
    assert (
        git_state(run_dir),
        warning["event"],
        warning["log_level"],
        warning["repo"],
        bool(warning["error"]) and "\n" not in warning["error"],
    ) == ((None, None), "git_state_unreadable", "warning", str(broken), True)


def test_wandb_mirror_gets_config_without_excluded_keys_and_finishes_at_exit(
    tmp_path, monkeypatch, fake_wandb
):
    at_exit = []
    monkeypatch.setattr(atexit, "register", at_exit.append)

    mirror_to_wandb(
        Run(), tmp_path / "r1", project="p", exclude={"api_key"}, system_stats=False
    )
    [finish] = at_exit
    finish()

    [run] = fake_wandb.runs
    assert (run.init["name"], run.init["config"], run.init["settings"]) == (
        "r1",
        {"seed": 1},
        {"x_disable_stats": True},
    )
    assert run.finished
