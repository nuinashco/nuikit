"""Fakes the tests share: an in-process stand-in for the `wandb` module."""

from __future__ import annotations

import sys
from typing import Any

import pytest
from attrs import define, field


@define
class FakeRun:
    """W&B run that keeps the arguments it started with."""

    init: dict[str, Any]
    finished: bool = False

    def finish(self) -> None:
        self.finished = True


@define
class FakeWandb:
    """Stand-in for the `wandb` module: each `init` starts a FakeRun."""

    Settings = staticmethod(dict)
    runs: list[FakeRun] = field(factory=list)

    def init(self, **kwargs: Any) -> FakeRun:
        self.runs.append(FakeRun(kwargs))
        return self.runs[-1]


@pytest.fixture
def fake_wandb(monkeypatch) -> FakeWandb:
    """Install a FakeWandb as the `wandb` module for one test."""
    wandb = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", wandb)
    return wandb
