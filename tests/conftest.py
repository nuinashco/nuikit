"""Fakes the tests share: an in-process stand-in for the `wandb` module."""

from __future__ import annotations

import sys
from types import SimpleNamespace
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


class FakeUsageError(Exception):
    """Stand-in for `wandb.errors.UsageError`."""


class FakeAuthenticationError(Exception):
    """Stand-in for `wandb.errors.AuthenticationError`."""


@define
class FakeWandb:
    """Stand-in for the `wandb` module: each `init` starts a FakeRun.

    With `refusal` set, `init` raises it instead, as W&B does without a login.
    """

    Settings = staticmethod(dict)
    errors = SimpleNamespace(
        UsageError=FakeUsageError, AuthenticationError=FakeAuthenticationError
    )
    runs: list[FakeRun] = field(factory=list)
    refusal: Exception | None = None

    def init(self, **kwargs: Any) -> FakeRun:
        if self.refusal is not None:
            raise self.refusal
        self.runs.append(FakeRun(kwargs))
        return self.runs[-1]


@pytest.fixture
def fake_wandb(monkeypatch) -> FakeWandb:
    """Install a FakeWandb as the `wandb` module for one test."""
    wandb = FakeWandb()
    monkeypatch.setitem(sys.modules, "wandb", wandb)
    monkeypatch.setitem(sys.modules, "wandb.errors", wandb.errors)
    return wandb
