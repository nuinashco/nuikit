"""Schema.from_hydra turns every config problem into one ConfigError."""

from __future__ import annotations

import pytest
from omegaconf import OmegaConf
from pydantic import PositiveInt, ValidationError

from nuikit.config import Schema
from nuikit.errors import ConfigError


class Toy(Schema):
    """Config with one constrained field."""

    steps: PositiveInt = 1


class Nested(Schema):
    """Config with a nested block."""

    toy: Toy
    name: str


class Named(Schema):
    """Config with one text field."""

    run_name: str


def test_unknown_and_invalid_fields_are_listed_one_per_line():
    with pytest.raises(ConfigError) as error:
        Toy.from_hydra(OmegaConf.create({"steps": 0, "stpes": 2}))

    lines = str(error.value).splitlines()
    assert [line.split(":")[0].strip() for line in lines[1:]] == ["steps", "stpes"]


def test_missing_mandatory_values_are_listed_together_by_their_full_keys():
    with pytest.raises(ConfigError) as error:
        Nested.from_hydra(OmegaConf.create({"toy": {"steps": "???"}, "name": "???"}))

    assert str(error.value) == (
        "missing values: name, toy.steps; set them in the entry config or as key=value"
    )


def test_unresolved_interpolation_is_a_config_error():
    with pytest.raises(ConfigError, match="invalid config"):
        Toy.from_hydra(OmegaConf.create({"steps": "${nowhere}"}))


def test_validated_config_is_read_only():
    config = Toy.from_hydra(OmegaConf.create({"steps": 3}))

    with pytest.raises(ValidationError):
        config.steps = 4


@pytest.mark.parametrize(
    ("given", "run_name"), [(7, "7"), (1e5, "100000.0")], ids=["int", "float"]
)
def test_text_field_takes_a_number_as_yaml_and_the_command_line_give_it(
    given, run_name
):
    config = Named.from_hydra(OmegaConf.create({"run_name": given}))

    assert config.run_name == run_name


def test_text_field_still_refuses_a_boolean():
    with pytest.raises(ConfigError, match="run_name: Input should be a valid string"):
        Named.from_hydra(OmegaConf.create({"run_name": True}))
