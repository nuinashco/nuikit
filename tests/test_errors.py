"""The CLI boundary reports user errors briefly and lets bugs crash."""

from __future__ import annotations

from typing import Self

import pytest
from omegaconf.errors import OmegaConfBaseException
from pydantic import BaseModel, PositiveInt, model_validator

from nuikit.errors import ConfigError, cli_boundary


def test_user_error_becomes_a_message_and_its_exit_code(capsys):
    @cli_boundary
    def command() -> None:
        raise ConfigError("no data; run `make data` first")

    with pytest.raises(SystemExit) as exit_info:
        command()

    assert exit_info.value.code == ConfigError.exit_code
    assert capsys.readouterr().err == "error: no data; run `make data` first\n"


def test_validation_error_is_a_config_error_with_one_line_per_field(capsys):
    class Settings(BaseModel):
        """Toy model."""

        steps: PositiveInt

    @cli_boundary
    def command() -> None:
        Settings.model_validate({"steps": 0})

    with pytest.raises(SystemExit) as exit_info:
        command()

    assert exit_info.value.code == ConfigError.exit_code
    assert capsys.readouterr().err.splitlines()[1].startswith("  steps: ")


def test_error_of_the_model_as_a_whole_is_its_message_without_a_path(capsys):
    class Span(BaseModel):
        """Toy model whose fields constrain each other."""

        low: float
        high: float

        @model_validator(mode="after")
        def _ordered(self) -> Self:
            if self.low >= self.high:
                raise ValueError("low must be below high")
            return self

    @cli_boundary
    def command() -> None:
        Span(low=2, high=1)

    with pytest.raises(SystemExit):
        command()

    assert capsys.readouterr().err == (
        "error: invalid Span:\n  Value error, low must be below high\n"
    )


@pytest.mark.parametrize(
    "text",
    ["", "\n    full_key: a.b\n    object_type=dict"],
    ids=["bare", "with-the-lines-omegaconf-appends"],
)
def test_omegaconf_error_without_a_message_is_named_by_its_class(capsys, text):
    @cli_boundary
    def command() -> None:
        raise OmegaConfBaseException(text)

    with pytest.raises(SystemExit) as exit_info:
        command()

    assert exit_info.value.code == ConfigError.exit_code
    assert capsys.readouterr().err == "error: invalid config: OmegaConfBaseException\n"


def test_bugs_keep_their_traceback():
    @cli_boundary
    def command() -> None:
        raise KeyError("bug")

    with pytest.raises(KeyError):
        command()
