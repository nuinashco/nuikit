"""A run directory records config, secrets masked, and provenance; W&B mirrors it."""

from __future__ import annotations

import atexit
import json

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


def test_start_run_writes_masked_config_and_provenance(tmp_path):
    run_dir = start_run(Run(), name="r1", runs_dir=tmp_path)

    config = OmegaConf.load(run_dir / "config.yaml")
    provenance = json.loads((run_dir / "run.json").read_text())
    assert (config.seed, config.api_key) == (1, "**********")
    assert set(provenance) == {"git_sha", "dirty", "argv", "started_at"}


def test_existing_run_directory_is_never_reused(tmp_path):
    start_run(Run(), name="r1", runs_dir=tmp_path)

    with pytest.raises(ConfigError, match="run_name"):
        start_run(Run(), name="r1", runs_dir=tmp_path)


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
