"""A run directory records config, secrets masked, and provenance; W&B mirrors it."""

from __future__ import annotations

import atexit
import json
import sys

import pytest
from omegaconf import OmegaConf
from pydantic import SecretStr

from nuikit.config import Schema
from nuikit.errors import ConfigError
from nuikit.runs import mirror_to_wandb, start_run


class Run(Schema):
    """Config with a secret."""

    seed: int = 1
    api_key: SecretStr = SecretStr("hunter2")


class Endpoint(Schema):
    """Nested config with a secret of its own."""

    password: SecretStr


class Stack(Schema):
    """Config with secrets: set, unset, in a nested schema, a mapping and a sequence."""

    api_key: SecretStr
    spare_key: SecretStr | None = None
    endpoint: Endpoint
    headers: dict[str, SecretStr]
    tokens: list[SecretStr]
    seed: int = 1


STACK = Stack.model_validate(
    {
        "api_key": "from-env",
        "endpoint": {"password": "from-env"},
        "headers": {"authorization": "from-env"},
        "tokens": ["from-env", "from-env"],
    }
)


def test_start_run_writes_masked_config_and_provenance(tmp_path):
    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path)

    config = OmegaConf.load(run_dir / "config.yaml")
    provenance = json.loads((run_dir / "run.json").read_text())
    assert (config.seed, config.api_key) == (1, "**********")
    assert set(provenance) == {"git_sha", "dirty", "argv", "started_at"}


@pytest.mark.parametrize(
    ("typed", "recorded"),
    [
        pytest.param("api_key=sk-1", "api_key=**********", id="field"),
        pytest.param("++api_key=sk-1", "++api_key=**********", id="forced"),
        pytest.param("~spare_key=sk-1", "~spare_key=**********", id="deleted"),
        pytest.param(
            "endpoint.password=sk-1", "endpoint.password=**********", id="nested-schema"
        ),
        pytest.param(
            "headers.authorization=sk-1",
            "headers.authorization=**********",
            id="mapping",
        ),
        pytest.param("tokens.1=sk-1", "tokens.1=**********", id="sequence"),
        pytest.param("tokens=[sk-1,sk-2]", "tokens=**********", id="whole-sequence"),
        pytest.param(
            "fallback.password=sk-1", "fallback.password=**********", id="same-name"
        ),
        pytest.param(
            "endpoint={password: sk-1}",
            "endpoint=**********",
            id="mapping-above-secret",
        ),
        pytest.param("endpoint=remote", "endpoint=remote", id="group-above-secret"),
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


def test_existing_run_directory_is_never_reused(tmp_path):
    start_run(Run(), name="r1", runs_dir=tmp_path)

    with pytest.raises(ConfigError, match="run_name"):
        start_run(Run(), name="r1", runs_dir=tmp_path)


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
