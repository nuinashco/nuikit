"""Structured logging: structlog over stdlib, console in a terminal, JSON elsewhere."""

from __future__ import annotations

import logging
import sys
from pathlib import PurePath
from typing import Any, Literal, cast

import numpy as np
import structlog

type LogLevel = Literal["debug", "info", "warning", "error"]
type LogFormat = Literal["auto", "console", "json"]


def configure_logging(*, level: LogLevel = "info", fmt: LogFormat = "auto") -> None:
    """Route structlog and stdlib loggers through one stderr handler.

    Call once, from the entry point; library code only calls `get_logger()`.
    """
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    as_json = fmt == "json" or (fmt == "auto" and not sys.stderr.isatty())
    rendering: list[structlog.typing.Processor] = (
        [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(default=_jsonable),
        ]
        if as_json
        else [structlog.dev.ConsoleRenderer()]
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                *rendering,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def _jsonable(value: object) -> object:
    """Return what the JSON renderer writes for a value that `json` cannot encode."""
    if isinstance(value, (np.generic, np.ndarray)):
        # The Python value of a scalar, the nested list of an array.
        return cast(Any, value).tolist()
    if isinstance(value, PurePath):
        return str(value)
    # The rest is structlog's own fallback, which `default` replaces.
    own_form = getattr(value, "__structlog__", None)
    return repr(value) if own_form is None else own_form()
