"""Logs from structlog and stdlib share one renderer: console on a TTY, else JSON."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pytest
import structlog

from nuikit.logging import configure_logging


class Shaped:
    """Value that gives structlog its own form."""

    def __structlog__(self) -> str:
        return "own form"


@pytest.fixture
def root_logger():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    root.handlers[:], root.level = handlers, level


def test_events_and_foreign_logs_render_as_json_lines(root_logger, capsys):
    configure_logging(level="info", fmt="json")

    structlog.stdlib.get_logger("app").info("run_started", seed=1)
    logging.getLogger("thirdparty").warning("plain %s", "message")

    first, second = (json.loads(line) for line in capsys.readouterr().err.splitlines())
    assert (first["event"], first["seed"], first["level"]) == ("run_started", 1, "info")
    assert (second["event"], second["logger"]) == ("plain message", "thirdparty")


def test_json_logs_write_numpy_values_and_paths_as_values_and_others_as_structlog_does(
    root_logger, capsys
):
    configure_logging(fmt="json")

    structlog.stdlib.get_logger("app").info(
        "metrics",
        loss=np.float32(0.5),
        step=np.int64(3),
        bins=np.arange(3),
        out=Path("runs/r1"),
        rate=complex(1, 2),
        shaped=Shaped(),
    )

    event = json.loads(capsys.readouterr().err)
    keys = ("loss", "step", "bins", "out", "rate", "shaped")
    assert [event[key] for key in keys] == [
        0.5,
        3,
        [0, 1, 2],
        "runs/r1",
        "(1+2j)",
        "own form",
    ]


@pytest.mark.parametrize(("tty", "as_json"), [(True, False), (False, True)])
def test_auto_format_is_console_on_a_terminal_and_json_elsewhere(
    root_logger, capsys, monkeypatch, tty, as_json
):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: tty)
    configure_logging(fmt="auto")

    structlog.stdlib.get_logger("app").info("run_started")

    err = capsys.readouterr().err
    assert ("run_started" in err, err.startswith("{")) == (True, as_json)
