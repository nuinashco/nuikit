"""Strict, read-only config models validated from Hydra-composed YAML."""

from __future__ import annotations

from typing import Self

from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException
from pydantic import BaseModel, ConfigDict, ValidationError

from nuikit.errors import ConfigError, describe, first_line


class Schema(BaseModel):
    """Base for config models: unknown keys are errors, values are read-only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_hydra(cls, cfg: DictConfig) -> Self:
        """Validate a composed Hydra config; raise ConfigError naming bad fields."""
        try:
            # `to_container` would stop at the first one and name its last segment only.
            if missing := sorted(OmegaConf.missing_keys(cfg)):
                raise ConfigError(
                    f"missing values: {', '.join(missing)}; "
                    "set them in the entry config or as key=value"
                )
            data = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
        except OmegaConfBaseException as e:
            raise ConfigError(first_line(e)) from e
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ConfigError(describe(e)) from e
