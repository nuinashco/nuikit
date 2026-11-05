"""Logs from structlog and stdlib share one renderer: console on a TTY, else JSON."""

from __future__ import annotations

import json
import logging
import sys

import pytest
import structlog

from nuikit.logging import configure_logging


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


@pytest.mark.parametrize(("tty", "as_json"), [(True, False), (False, True)])
def test_auto_format_is_console_on_a_terminal_and_json_elsewhere(
    root_logger, capsys, monkeypatch, tty, as_json
):
    monkeypatch.setattr(sys.stderr, "isatty", lambda: tty)
    configure_logging(fmt="auto")

    structlog.stdlib.get_logger("app").info("run_started")

    err = capsys.readouterr().err
    assert ("run_started" in err, err.startswith("{")) == (True, as_json)
